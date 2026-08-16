import os
import shutil
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

# Token simple para que no cualquiera use tu servidor gratis
API_TOKEN = os.environ.get("API_TOKEN", "cambia-esto-por-algo-secreto")


def check_auth(req):
    token = req.headers.get("X-API-Token", "")
    return token == API_TOKEN


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/debug", methods=["GET"])
def debug_formats():
    if not check_auth(request):
        return jsonify({"error": "unauthorized"}), 401

    query = request.args.get("q")
    video_id = request.args.get("video_id")
    if not query and not video_id:
        return jsonify({"error": "falta 'q' o 'video_id'"}), 400

    target = f"https://www.youtube.com/watch?v={video_id}" if video_id else f"ytsearch1:{query}"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        },
    }

    secret_cookies_path = "/etc/secrets/cookies.txt"
    tmp_cookies_path = "/tmp/cookies.txt"
    cookies_info = {
        "secret_file_existe": os.path.exists(secret_cookies_path),
        "tmp_file_existe": os.path.exists(tmp_cookies_path),
    }
    if os.path.exists(secret_cookies_path):
        cookies_info["secret_file_tamano_bytes"] = os.path.getsize(secret_cookies_path)
        if not os.path.exists(tmp_cookies_path):
            shutil.copyfile(secret_cookies_path, tmp_cookies_path)
        ydl_opts["cookiefile"] = tmp_cookies_path
        cookies_info["cookiefile_usado"] = tmp_cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target, download=False)
            if "entries" in info:
                if not info["entries"]:
                    return jsonify({"error": "sin resultados"}), 404
                info = info["entries"][0]

            formats = info.get("formats", [])
            resumen = [
                {
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "acodec": f.get("acodec"),
                    "vcodec": f.get("vcodec"),
                    "abr": f.get("abr"),
                    "protocol": f.get("protocol"),
                }
                for f in formats
            ]
            return jsonify({
                "video_id": info.get("id"),
                "title": info.get("title"),
                "total_formats": len(formats),
                "formats": resumen,
                "cookies_info": cookies_info,
            })
    except Exception as e:
        return jsonify({"error": str(e), "cookies_info": cookies_info}), 500


@app.route("/audio", methods=["GET"])
def get_audio():
    if not check_auth(request):
        return jsonify({"error": "unauthorized"}), 401

    query = request.args.get("q")
    video_id = request.args.get("video_id")

    if not query and not video_id:
        return jsonify({"error": "falta 'q' o 'video_id'"}), 400

    target = f"https://www.youtube.com/watch?v={video_id}" if video_id else f"ytsearch1:{query}"

    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        },
    }

    # Si subiste un cookies.txt como Secret File en Render, se usa automáticamente.
    # Render monta los Secret Files como solo-lectura, pero yt-dlp necesita poder
    # escribir el archivo de cookies, así que lo copiamos a /tmp (sí es escribible).
    secret_cookies_path = "/etc/secrets/cookies.txt"
    tmp_cookies_path = "/tmp/cookies.txt"
    if os.path.exists(secret_cookies_path):
        if not os.path.exists(tmp_cookies_path):
            shutil.copyfile(secret_cookies_path, tmp_cookies_path)
        ydl_opts["cookiefile"] = tmp_cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target, download=False)
            # Si venía de búsqueda, coge el primer resultado
            if "entries" in info:
                if not info["entries"]:
                    return jsonify({"error": "sin resultados"}), 404
                info = info["entries"][0]

            audio_url = info.get("url")
            if not audio_url:
                # Buscar en 'formats' si no vino directo
                for f in info.get("formats", []):
                    if f.get("acodec") != "none" and f.get("url"):
                        audio_url = f["url"]
                        break

            if not audio_url:
                return jsonify({"error": "no se encontró stream de audio"}), 404

            return jsonify({
                "video_id": info.get("id"),
                "title": info.get("title"),
                "audio_url": audio_url,
                "duration": info.get("duration"),
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
