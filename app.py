import os
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
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

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
