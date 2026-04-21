"""``lvt-cert gen-keys`` — generate an RSA keypair for QR signing.

Writes ``private_key.pem`` and ``public_key.pem`` into the current project.
The private key is the signing secret for the QR payload; commit **only** the
public key so verifiers can check signatures. The private key should be added
to ``.gitignore`` and loaded via env var (``QR_PRIVATE_KEY_PATH``) in
production.
"""

from __future__ import annotations

from pathlib import Path

import typer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from rich.console import Console

app = typer.Typer(help="Generate RSA keypair for QR signing.")
console = Console()

DEFAULT_KEY_SIZE = 2048


@app.callback(invoke_without_command=True)
def gen_keys(
    out_dir: Path = typer.Option(Path.cwd(), "--out", "-o", help="Directory to write keys into."),
    key_size: int = typer.Option(DEFAULT_KEY_SIZE, help="RSA key size in bits."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing keys."),
) -> None:
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    priv_path = out_dir / "private_key.pem"
    pub_path = out_dir / "public_key.pem"

    if (priv_path.exists() or pub_path.exists()) and not force:
        console.print(f"[red]✗ keys already exist in {out_dir}. Use --force to overwrite.[/]")
        raise typer.Exit(code=1)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    priv_path.write_bytes(priv_pem)
    pub_path.write_bytes(pub_pem)

    console.print(f"[green]✓[/] private key → {priv_path}")
    console.print(f"[green]✓[/] public  key → {pub_path}")
    console.print("[yellow]![/] add [cyan]private_key.pem[/] to .gitignore — never commit it.")
