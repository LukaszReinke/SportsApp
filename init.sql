IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'SportsApp_db')
BEGIN
    CREATE DATABASE SportsApp_db;
END
