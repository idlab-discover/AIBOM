-- Ensure mlmd user exists with mysql_native_password and permissions
CREATE USER IF NOT EXISTS 'mlmd'@'%' IDENTIFIED WITH mysql_native_password BY 'mlmdpass';
CREATE DATABASE IF NOT EXISTS `mlmd` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON `mlmd`.* TO 'mlmd'@'%';
FLUSH PRIVILEGES;
