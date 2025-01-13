# Użyj oficjalnej wersji Pythona
FROM python:3.10-slim

# Ustaw katalog roboczy
WORKDIR /app

# Instalacja zależności systemowych
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    unixodbc-dev \
    curl \
    gnupg2 \
    && rm -rf /var/lib/apt/lists/*

# Instalacja sterownika ODBC
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Skopiuj pliki do obrazu
COPY . .

# Zainstaluj zależności aplikacji
RUN pip install --no-cache-dir -r requirements.txt

# Eksponuj port aplikacji
EXPOSE 8000

# Ustaw domyślną komendę
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
