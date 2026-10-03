FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PORT=8080
ENV DB_PATH=/data/platform_b.db
RUN mkdir -p /data
EXPOSE 8080
CMD ["python3", "server.py"]
