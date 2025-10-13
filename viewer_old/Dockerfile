FROM node:20-alpine

WORKDIR /viewer

# Install dependencies
COPY package.json /viewer/
RUN npm install --omit=dev

# Copy server
COPY server.js /viewer/

EXPOSE 8080

CMD ["npm", "start"]
