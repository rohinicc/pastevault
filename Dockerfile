FROM python:3.12-slim

RUN addgroup --system pastevault && adduser --system --ingroup pastevault --no-create-home pastevault

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=pastevault:pastevault . .

EXPOSE 8000

USER pastevault

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
