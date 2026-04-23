FROM archive-base

WORKDIR /app

# Copy only requirements first (cache)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy full app
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]