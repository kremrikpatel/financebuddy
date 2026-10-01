FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY . .
# Baked in at build time: where the browser reaches the API, and whether to show the demo login.
ARG VITE_API_URL=/api/v1
ARG VITE_DEMO_MODE=false
ENV VITE_API_URL=$VITE_API_URL VITE_DEMO_MODE=$VITE_DEMO_MODE
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY package.json ./
RUN npm install vite@^5 --no-audit --no-fund
EXPOSE 5173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
