# صورة تشغيل المشروع — تحوّط «خدمة قابلة للنشر» (يوم 5)
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# منفذ خدمة FastAPI
EXPOSE 8000

# افتراضيًا: شغّل الخدمة (POST /process، GET /metrics، GET /healthz)
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
