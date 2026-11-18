"""Bundle de evidência é verificável por hash (Frente C).

Bug pego na revisão: ao decifrar no bundle, o arquivo (texto claro) deixava de bater com
o `sha256` do manifesto (hash do ciphertext). Um bundle que não confere o próprio hash
não serve de prova. O conserto: o bundle empacota os bytes ARMAZENADOS; o manifesto diz
`encrypted` e o destinatário decifra offline. Este teste afirma que arquivo e manifesto
batem — reverter para o texto decifrado reprova.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from orchestrator.api import deps
from orchestrator.config import settings
from orchestrator.domain.roles import Role
from orchestrator.evidence import store
from orchestrator.main import app
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import EvidenceSnapshotRow


async def test_bundle_hashes_batem_com_os_arquivos(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    chave = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "SECRETS_KEY", chave)
    await init_db()

    scan_id = uuid.uuid4()
    ref = store.put("corpo com alvo@banco.com.br", encrypt=True)
    async with session() as s:
        s.add(
            EvidenceSnapshotRow(
                sha256=ref.sha256,
                original_sha256=ref.original_sha256,
                encrypted=True,
                size_bytes=ref.size_bytes,
                scan_id=scan_id,
            )
        )
        await s.commit()

    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="u1", email="admin@x", role=Role.ADMIN, is_service=True
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            resp = await client.get(f"/evidence/bundle/{scan_id}")
    finally:
        app.dependency_overrides.pop(deps.get_principal, None)

    assert resp.status_code == 200, resp.text
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["blobs"], "manifesto sem blobs"
    for entry in manifest["blobs"]:
        conteudo = zf.read(entry["path"])
        # O arquivo no zip bate com o sha256 do manifesto (integridade do bundle).
        assert hashlib.sha256(conteudo).hexdigest() == entry["sha256"]
        assert entry["encrypted"] is True
        # E o ciphertext empacotado decifra de volta ao original (recuperável offline).
        assert Fernet(chave.encode()).decrypt(conteudo).decode() == "corpo com alvo@banco.com.br"
