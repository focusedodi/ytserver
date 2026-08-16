FROM python:3.11-slim

# curl + unzip hacen falta para instalar Deno
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instala Deno (el runtime de JS que yt-dlp necesita para YouTube desde
# finales de 2025). Queda en /root/.deno/bin/deno
ENV DENO_INSTALL="/root/.deno"
RUN curl -fsSL https://deno.land/install.sh | sh
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Le decimos a la app exactamente donde quedo el binario de deno,
# para no depender de que el PATH se herede bien en tiempo de ejecucion.
ENV JS_RUNTIME_PATH="/root/.deno/bin/deno"

EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "--timeout", "120", "app:app"]
