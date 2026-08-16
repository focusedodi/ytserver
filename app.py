import os
import shutil
import logging
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Token simple para que no cualquiera use tu servidor gratis
API_TOKEN = os.environ.get("API_TOKEN", "cambia-esto-por-algo-secreto")

SECRET_COOKIES_PATH = "/etc/secrets/cookies.txt"
TMP_COOKIES_PATH = "/tmp/cookies.txt"

# Runtime de JS que yt-dlp usa para resolver los challenges de YouTube.
# Desde finales de 2025 esto es obligatorio para que YouTube entregue
# formatos reales (si no, aunque cookies y player_client estén bien,
# revienta con "Requested format is not available").
# Se puede sobreescribir con la env var JS_RUNTIME si el binario de Deno
# vive en otra ruta.
JS_RUNTIME_PATH = os.environ.get("JS_RUNTIME_PATH", "deno")

# Distintas combinaciones de "cliente" que yt-dlp puede simular.
# Probamos varias en orden porque YouTube va bloqueando unas y otras
# van cambiando de efectividad casi cada semana. "tv" y "default" se
# agregaron porque son las que mejor sobreviven a los cambios de 2026.
PLAYER_CLIENT_ATTEMPTS = [
    ["default"],
    ["tv"],
    ["ios"],
    ["android"],
    ["web_creator"],
    ["android", "web"],
    ["web"],
]


def check_auth(req):
    token = req.headers.get("X-API-Token", "")
    return token == API_TOKEN


def refresh_tmp_cookies():
    """Copia siempre el cookies.txt del Secret File a /tmp (que sí es escribible)."""
    cookies_info = {
        "secret_file_existe": os.path.exists(SECRET_COOKIES_PATH),
    }
    if os.path.exists(SECRET_COOKIES_PATH):
        stat = os.stat(SECRET_COOKIES_PATH)
        cookies_info["secret_file_tamano_bytes"] = stat.st_size
        cookies_info["secret_file_modificado_hace_segundos"] = int(
            __import__("time").time() - stat.st_mtime
        )
        try:
            shutil.copyfile(SECRET_COOKIES_PATH, TMP_COOKIES_PATH)
            cookies_info["cookiefile_usado"] = TMP_COOKIES_PATH
        except Exception as e:
            cookies_info["error_copiando_cookies"] = str(e)
    return cookies_info


def build_base_opts(cookies_info):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # Le decimos a yt-dlp qué runtime de JS usar para resolver los
        # challenges de YouTube. Sin esto, muchos formatos vienen sin URL.
        # OJO: el formato correcto es un dict {runtime: {config}}, una
        # lista simple hace que yt-dlp falle al instanciar YoutubeDL.
        "js_runtimes": {"deno": {"path": JS_RUNTIME_PATH} if JS_RUNTIME_PATH != "deno" else {}},
    }
    if cookies_info.get("cookiefile_usado"):
        opts["cookiefile"] = cookies_info["cookiefile_usado"]
    return opts


def extract_with_fallback(target, base_opts):
    """Intenta extraer info probando distintos player_client en orden.
    Devuelve (info, client_usado, errores_por_intento).
    Si todos fallan, lanza una excepcion con el detalle de cada intento
    (antes solo se veia el error del ultimo, lo que hacia el debug casi
    imposible).
    """
    errors = {}
    for clients in PLAYER_CLIENT_ATTEMPTS:
        opts = dict(base_opts)
        opts["extractor_args"] = {"youtube": {"player_client": clients}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=False)
                logger.info("Exito con player_client=%s", clients)
                return info, clients, errors
        except Exception as e:
            logger.warning("Fallo con player_client=%s -> %s", clients, e)
            errors[",".join(clients)] = str(e)
            continue
    raise RuntimeError(f"Todos los player_client fallaron: {errors}")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/version", methods=["GET"])
def version():
    """Util para confirmar en produccion que version de yt-dlp esta
    corriendo y si Deno (el runtime de JS) esta disponible."""
    if not check_auth(request):
        return jsonify({"error": "unauthorized"}), 401

    deno_path = shutil.which(JS_RUNTIME_PATH)
    return jsonify({
        "yt_dlp_version": yt_dlp.version.__version__,
        "js_runtime_configurado": JS_RUNTIME_PATH,
        "js_runtime_encontrado_en": deno_path,
        "js_runtime_disponible": deno_path is not None,
    })


@app.route("/debug", methods=["GET"])
def debug_formats():
    if not check_auth(request):
        return jsonify({"error": "unauthorized"}), 401

    query = request.args.get("q")
    video_id = request.args.get("video_id")
    if not query and not video_id:
        return jsonify({"error": "falta 'q' o 'video_id'"}), 400

    target = f"https://www.youtube.com/watch?v={video_id}" if video_id else f"ytsearch1:{query}"

    cookies_info = refresh_tmp_cookies()
    base_opts = build_base_opts(cookies_info)

    try:
        info, client_usado, intentos_fallidos = extract_with_fallback(target, base_opts)
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
            "player_client_usado": client_usado,
            "intentos_fallidos_antes_de_exito": intentos_fallidos,
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

    cookies_info = refresh_tmp_cookies()
    base_opts = build_base_opts(cookies_info)
    base_opts["format"] = "bestaudio/best"

    try:
        info, client_usado, intentos_fallidos = extract_with_fallback(target, base_opts)

        if "entries" in info:
            if not info["entries"]:
                return jsonify({"error": "sin resultados"}), 404
            info = info["entries"][0]

        audio_url = info.get("url")
        if not audio_url:
            for f in info.get("formats", []):
                if f.get("acodec") != "none" and f.get("url"):
                    audio_url = f["url"]
                    break

        if not audio_url:
            return jsonify({
                "error": "no se encontro stream de audio",
                "cookies_info": cookies_info,
                "intentos_fallidos": intentos_fallidos,
            }), 404

        return jsonify({
            "video_id": info.get("id"),
            "title": info.get("title"),
            "audio_url": audio_url,
            "duration": info.get("duration"),
            "player_client_usado": client_usado,
        })

    except Exception as e:
        return jsonify({"error": str(e), "cookies_info": cookies_info}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
