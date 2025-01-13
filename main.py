import secrets
import string
from datetime import timedelta, datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, Form, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from email.mime.text import MIMEText
import aiosmtplib
import base64

# Konfiguracja aplikacji FastAPI
app = FastAPI()

# Konfiguracja JWT
SECRET_KEY = "secret_key"  # Zastąpić bardziej skomplikowanym kluczem i umieścić go w innym miejscu
ALGORITHM = "HS256"  # Algorytm podpisu JWT
TOKEN_EXPIRE_MINUTES = 30

# Konfiguracja bazy danych
DATABASE_URL = "mssql+pyodbc://sa:SportsApp123!@sql_edge:1433/SportsApp_db?driver=ODBC+Driver+17+for+SQL+Server"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Hashowanie hasł
crypt_context = CryptContext(schemes=["bcrypt"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user")  # Domyślna rola użytkownika
    created_at = Column(DateTime, default=datetime.utcnow)
    is_approved = Column(Boolean, default=False)  # Czy zatwierdzony przez admina
    is_first_login = Column(Boolean, default=True)  # Czy pierwsze logowanie


class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    firm = Column(String(255), nullable=True)
    description = Column(String, nullable=True)
    title = Column(String(255), nullable=False)
    event_date_from = Column(DateTime, nullable=False)
    event_date_to = Column(DateTime, nullable=False)
    photo = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    firm = Column(String(255), nullable=True)
    date_from = Column(DateTime, nullable=False)
    date_to = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Tworzenie tabel (migracja)
Base.metadata.create_all(bind=engine)


class ApplicationCreate(BaseModel):
    first_name: str
    last_name: str
    firm: str | None = None
    description: str | None = None
    title: str
    event_date_from: datetime
    event_date_to: datetime
    photo: str

    @field_validator("photo")
    def validate_photo(cls, value):
        try:
            base64.b64decode(value)
        except Exception:
            raise ValueError("Invalid Base64 string")
        return value


class AnnouncementCreate(BaseModel):
    title: str
    description: str
    firm: str | None = None
    date_from: datetime
    date_to: datetime


class AnnouncementUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    firm: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


# Pomoce dla uwierzytelniania
def verify_password(plain_password, hashed_password):
    return crypt_context.verify(plain_password, hashed_password)


def hash_password(password):
    return crypt_context.hash(password)


def generate_password(length=8):
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(characters) for _ in range(length))


def create_access_token(username: str, role: str):
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "role": role,
        "exp": expires
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def send_email_async(recipient_email: str, subject: str, body: str):
    sender_email = ""  # Twój adres e-mail
    sender_password = ""  # Twoje hasło do e-maila

    # Utwórz wiadomość e-mail
    message = MIMEText(body)
    message["From"] = f"Łukasz Reinke <{sender_email}>"
    message["To"] = recipient_email
    message["Subject"] = subject
    message["Reply-To"] = sender_email
    message["Return-Path"] = sender_email

    # Wyślij e-mail za pomocą SMTP
    await aiosmtplib.send(
        message,
        hostname="smtp.gmail.com",  # Zamień na serwer SMTP swojego dostawcy
        port=587,                     # Zazwyczaj 587 dla TLS
        username=sender_email,
        password=sender_password,
        start_tls=True                # Użycie TLS
    )


# Dependency to manage database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/login/", response_model=dict)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_approved:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account not approved by admin")

    if user.is_first_login:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please change your password on first login")

    access_token = create_access_token(user.username, user.role)
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/add_user/", response_model=dict)
def add_user(username: str, email: EmailStr, role: str = "organizer", db: Session = Depends(get_db)):
    initial_password = generate_password()
    hashed_password = hash_password(initial_password)

    new_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role,
        created_at=datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"username": username, "email": email, "role": role, "password": initial_password}


@app.post("/change_password/", response_model=dict)
def change_password(
    old_password: str, new_password: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(old_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid old password")

    user.hashed_password = hash_password(new_password)
    user.is_first_login = False  # Wyłącz tryb pierwszego logowania
    db.commit()

    return {"message": "Password has been changed successfully."}


@app.post("/add_super_admin/", response_model=dict)
def add_super_admin(username: str, email: EmailStr, password: str, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email already exists")

    new_user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),  # Hasło zostanie wygenerowane po zatwierdzeniu
        is_approved=True,  # Użytkownik musi być zatwierdzony przez admina
        is_first_login=False,  # Pierwsze logowanie
        created_at=datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Your account has been created. Please wait for admin approval."
    }


@app.post("/register/", response_model=dict)
def register_user(username: str, email: EmailStr, db: Session = Depends(get_db)):
    # Sprawdź, czy użytkownik już istnieje
    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email already exists")

    # Dodaj nowego użytkownika
    new_user = User(
        username=username,
        email=email,
        hashed_password="",  # Hasło zostanie wygenerowane po zatwierdzeniu
        is_approved=False,  # Użytkownik musi być zatwierdzony przez admina
        is_first_login=True,  # Pierwsze logowanie
        created_at=datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Your account has been created. Please wait for admin approval."
    }


@app.get("/users_to_approve/", response_model=list[dict])
def get_users_to_approve(db: Session = Depends(get_db)):
    users = db.query(User).filter(User.is_approved == False).all()
    return [{"id": user.id, "username": user.username, "email": user.email} for user in users]


@app.post("/send_email/")
async def send_email_endpoint():
    await send_email_async(
        recipient_email="s22461@pjwstk.edu.pl",
        subject="Your account has been approved",
        body="Siemanko"
    )


@app.post("/approve_user/", response_model=dict)
async def approve_user(user_id: int, db: Session = Depends(get_db)):
    # Pobierz użytkownika
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_approved:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already approved")

    # Generuj hasło
    generated_password = generate_password()
    hashed_password = hash_password(generated_password)

    # Zaktualizuj dane użytkownika
    user.is_approved = True
    user.hashed_password = hashed_password
    db.commit()

    # Wyślij e-mail z hasłem
    email_body = f"""
    Hello {user.username},

    Your account has been approved by the admin. You can now log in using the following credentials:

    Username: {user.username}
    Password: {generated_password}

    Best regards,
    The Team
    """
    await send_email_async(
        recipient_email=user.email,
        subject="Your account has been approved",
        body=email_body
    )

    return {"message": f"User {user.username} has been approved and notified by email."}


@app.post("/applications/", response_model=dict)
def create_application(application: ApplicationCreate, db: Session = Depends(get_db)):
    new_application = Application(
        first_name=application.first_name,
        last_name=application.last_name,
        firm=application.firm,
        description=application.description,
        title=application.title,
        event_date_from=application.event_date_from,
        event_date_to=application.event_date_to,
        photo=application.photo,
        created_at=datetime.utcnow()
    )
    db.add(new_application)
    db.commit()
    db.refresh(new_application)

    return {
        "message": "Application created successfully",
        "application_id": new_application.id
    }


@app.post("/announcements-create/", response_model=dict)
def create_announcement(
    announcement: AnnouncementCreate, db: Session = Depends(get_db)
):
    new_announcement = Announcement(
        title=announcement.title,
        description=announcement.description,
        firm=announcement.firm,
        date_from=announcement.date_from,
        date_to=announcement.date_to,
        created_at=datetime.utcnow()
    )
    db.add(new_announcement)
    db.commit()
    db.refresh(new_announcement)
    return {"message": "Announcement created successfully", "id": new_announcement.id}


@app.put("/announcements-update/{announcement_id}/", response_model=dict)
def update_announcement(
    announcement_id: int,
    update_data: AnnouncementUpdate,
    db: Session = Depends(get_db)
):
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if update_data.title is not None:
        announcement.title = update_data.title
    if update_data.description is not None:
        announcement.description = update_data.description
    if update_data.firm is not None:
        announcement.firm = update_data.firm
    if update_data.date_from is not None:
        announcement.date_from = update_data.date_from
    if update_data.date_to is not None:
        announcement.date_to = update_data.date_to

    db.commit()
    db.refresh(announcement)
    return {"message": "Announcement updated successfully"}


@app.delete("/announcements-delete/{announcement_id}/", response_model=dict)
def delete_announcement(announcement_id: int, db: Session = Depends(get_db)):
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    db.delete(announcement)
    db.commit()
    return {"message": "Announcement deleted successfully"}





