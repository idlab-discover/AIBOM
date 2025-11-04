import path from 'node:path';
import winston from 'winston';

// Always resolve logs directory relative to the project root
const logDir = path.resolve(__dirname, '../../logs');

const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.printf(({ timestamp, level, message }) => {
      return `${timestamp} ${level.toUpperCase()}: ${message}`;
    })
  ),
  transports: [
    new winston.transports.File({ filename: path.join(logDir, 'bom-viewer.log') }),
  ],
});

export default logger;
