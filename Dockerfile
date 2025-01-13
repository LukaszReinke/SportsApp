# Użyj oficjalnej wersji Pythona
FROM python:3.10-slim

# Ustaw katalog roboczy
WORKDIR /app

# Instalacja zależności systemowych
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Skopiuj pliki do obrazu
COPY . /app

# Zainstaluj zależności aplikacji
RUN pip install --no-cache-dir -r requirements.txt

# Ustaw domyślną komendę
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Instalacja niezbędnych pakietów i sterowników ODBC
RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    unixodbc-dev && \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
