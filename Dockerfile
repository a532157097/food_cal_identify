FROM node:22-bookworm-slim AS h5
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js shims-uni.d.ts ./
COPY src ./src
RUN npm run build:h5

FROM python:3.11-slim
WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt
COPY server /app/server
COPY --from=h5 /src/dist/build/h5 /app/h5
ENV H5_DIST_DIR=/app/h5
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
