from __future__ import annotations

import os
from typing import Any, Dict

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

import backend


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2MB


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/deploy")
def deploy():
    upload_dir = backend.ensure_upload_dir()
    pem = request.files.get("pem")
    if pem is None or pem.filename is None or pem.filename.strip() == "":
        return jsonify({"error": "Missing PEM file"}), 400

    filename = secure_filename(pem.filename)
    pem_path = os.path.join(upload_dir, filename)
    pem.save(pem_path)

    username = request.form.get("username", "").strip()
    deployer_ip = request.form.get("deployer_ip", "").strip()
    sh1_ip = request.form.get("sh1_ip", "").strip()
    sh2_ip = request.form.get("sh2_ip", "").strip()
    sh3_ip = request.form.get("sh3_ip", "").strip()
    splunk_admin_password = request.form.get("splunk_admin_password", "").strip()
    shc_secret = request.form.get("shc_secret", "").strip()
    force_sh1_captain = request.form.get("force_sh1_captain", "on") == "on"

    if not (username and deployer_ip and sh1_ip and sh2_ip and sh3_ip and splunk_admin_password):
        return jsonify({"error": "username, deployer_ip, sh1_ip, sh2_ip, sh3_ip, splunk_admin_password are required"}), 400

    job = backend.start_deploy_job(
        pem_path=pem_path,
        username=username,
        deployer_ip=deployer_ip,
        sh1_ip=sh1_ip,
        sh2_ip=sh2_ip,
        sh3_ip=sh3_ip,
        splunk_admin_password=splunk_admin_password,
        shc_secret=shc_secret,
        force_sh1_captain=force_sh1_captain,
    )
    return redirect(url_for("job_page", job_id=job.id))


@app.post("/deploy-app")
def deploy_app():
    upload_dir = backend.ensure_upload_dir()
    pem = request.files.get("pem_app")
    if pem is None or pem.filename is None or pem.filename.strip() == "":
        return jsonify({"error": "Missing PEM file"}), 400

    filename = secure_filename(pem.filename)
    pem_path = os.path.join(upload_dir, filename)
    pem.save(pem_path)

    username = request.form.get("username_app", "").strip()
    deployer_ip = request.form.get("deployer_ip_app", "").strip()
    captain_ip = request.form.get("captain_ip_app", "").strip()
    splunk_admin_password = request.form.get("splunk_admin_password_app", "").strip()
    app_folder_name = request.form.get("app_folder_name", "").strip()

    if not (username and deployer_ip and captain_ip and splunk_admin_password and app_folder_name):
        return jsonify({"error": "username, deployer_ip, captain_ip, splunk_admin_password, app_folder_name are required"}), 400

    job = backend.start_deploy_app_job(
        pem_path=pem_path,
        username=username,
        deployer_ip=deployer_ip,
        captain_ip=captain_ip,
        splunk_admin_password=splunk_admin_password,
        app_folder_name=app_folder_name,
    )
    return redirect(url_for("job_page", job_id=job.id))


@app.get("/jobs/<job_id>")
def job_page(job_id: str):
    job = backend.get_job(job_id)
    if job is None:
        return "Job not found", 404
    return render_template("job.html", job_id=job_id)


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    job = backend.get_job(job_id)
    if job is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(
        {
            "id": job.id,
            "kind": job.kind,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "logs": job.logs[-300:],
            "result": job.result,
            "error": job.error,
        }
    )


if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("APP_PORT", "5000"))
    debug = os.environ.get("APP_DEBUG", "0").strip() in ("1", "true", "True", "yes", "on")
    app.run(host=host, port=port, debug=debug)
