"""The replay CLI.

A thin Typer client over the REST API. Output uses Rich tables in the
instrument style: hard rules, monospaced numbers, lime and coral accents.
Every command is org scoped through the stored token.
"""

from __future__ import annotations

import sys
from typing import Annotated

import httpx
import jwt
import typer
from rich import box
from rich.console import Console
from rich.table import Table

from replay.cli import config as cfg

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Replay CLI.")
orgs_app = typer.Typer(no_args_is_help=True, help="Org commands.")
keys_app = typer.Typer(no_args_is_help=True, help="Replay API key commands.")
providers_app = typer.Typer(no_args_is_help=True, help="Provider key (BYOK) commands.")
logs_app = typer.Typer(no_args_is_help=True, help="Request log commands.")
cost_app = typer.Typer(no_args_is_help=True, help="Cost commands.")
auth_app = typer.Typer(no_args_is_help=True, help="Auth helpers.")
app.add_typer(orgs_app, name="orgs")
app.add_typer(keys_app, name="keys")
app.add_typer(providers_app, name="providers")
app.add_typer(logs_app, name="logs")
app.add_typer(cost_app, name="cost")
app.add_typer(auth_app, name="auth")

console = Console()
LIME = "#C5F82A"
CORAL = "#FF4D2E"


def _client(require_auth: bool = True) -> httpx.Client:
    config = cfg.load()
    if require_auth and not config.token:
        console.print("[bold]not logged in[/bold]. Run: replay login --token <jwt>")
        raise typer.Exit(code=1)
    headers: dict[str, str] = {}
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"
    if config.org_id:
        headers["X-Replay-Org"] = config.org_id
    return httpx.Client(base_url=config.api_url, headers=headers, timeout=30)


def _fail(resp: httpx.Response) -> None:
    detail: str
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:  # noqa: BLE001
        detail = resp.text
    console.print(f"[{CORAL}]error {resp.status_code}[/]: {detail}")
    raise typer.Exit(code=1)


def _table(title: str, columns: list[str]) -> Table:
    t = Table(title=title, box=box.SQUARE, header_style=f"bold {LIME}", title_justify="left")
    for c in columns:
        t.add_column(c)
    return t


# --- top level ---------------------------------------------------------------


@app.command()
def login(
    token: Annotated[str, typer.Option(help="A Supabase JWT, or a dev token.")],
    api_url: Annotated[str | None, typer.Option(help="API base URL.")] = None,
) -> None:
    """Store the bearer token used for management calls."""
    config = cfg.load()
    config.token = token
    if api_url:
        config.api_url = api_url
    cfg.save(config)
    console.print(f"[{LIME}]logged in[/]. token stored.")


@app.command()
def logout() -> None:
    """Remove the stored token and org."""
    cfg.clear()
    console.print("logged out.")


@auth_app.command("dev-token")
def dev_token(
    user_id: Annotated[str, typer.Option(help="A UUID for the user.")],
    email: Annotated[str, typer.Option()] = "dev@example.com",
) -> None:
    """Mint an unsigned dev JWT for local use (auth fallback only, never prod)."""
    # A 32+ byte key avoids the HMAC length warning. The signature is not
    # verified in the local fallback, so the value itself does not matter.
    secret = "replay-local-dev-secret-not-for-production"
    token = jwt.encode({"sub": user_id, "email": email}, secret, algorithm="HS256")
    # Plain echo, not Rich, so the token is one unwrapped line for piping.
    typer.echo(token)


# --- orgs --------------------------------------------------------------------


@orgs_app.command("create")
def orgs_create(
    name: Annotated[str, typer.Option()],
    slug: Annotated[str, typer.Option()],
) -> None:
    """Create an org and store it as the active org."""
    with _client() as client:
        resp = client.post("/api/orgs", json={"name": name, "slug": slug})
    if resp.status_code >= 400:
        _fail(resp)
    org = resp.json()
    config = cfg.load()
    config.org_id = org["id"]
    cfg.save(config)
    console.print(f"[{LIME}]created[/] org {org['slug']} ({org['id']}) and set it active.")


@orgs_app.command("current")
def orgs_current() -> None:
    """Show the active org."""
    with _client() as client:
        resp = client.get("/api/orgs/current")
    if resp.status_code >= 400:
        _fail(resp)
    org = resp.json()
    console.print(f"{org['name']}  [{LIME}]{org['slug']}[/]  {org['id']}")


@orgs_app.command("use")
def orgs_use(org_id: str) -> None:
    """Set the active org id (sent as X-Replay-Org)."""
    config = cfg.load()
    config.org_id = org_id
    cfg.save(config)
    console.print(f"active org set to {org_id}")


# --- keys --------------------------------------------------------------------


@keys_app.command("create")
def keys_create(name: str) -> None:
    """Create a Replay API key. The secret is shown once."""
    with _client() as client:
        resp = client.post("/api/keys", json={"name": name})
    if resp.status_code >= 400:
        _fail(resp)
    key = resp.json()
    console.print(f"[{LIME}]new key[/] (store it now, it is not shown again):")
    typer.echo(key["key"])


@keys_app.command("list")
def keys_list() -> None:
    with _client() as client:
        resp = client.get("/api/keys")
    if resp.status_code >= 400:
        _fail(resp)
    table = _table("API KEYS", ["prefix", "name", "created", "last used", "revoked"])
    for k in resp.json():
        table.add_row(
            k["prefix"], k["name"], k["created_at"][:19],
            (k["last_used_at"] or "-")[:19], (k["revoked_at"] or "-")[:19],
        )
    console.print(table)


@keys_app.command("revoke")
def keys_revoke(key_id: str) -> None:
    with _client() as client:
        resp = client.post(f"/api/keys/{key_id}/revoke")
    if resp.status_code >= 400:
        _fail(resp)
    console.print("revoked.")


# --- providers ---------------------------------------------------------------


@providers_app.command("add")
def providers_add(
    provider: str,
    label: str,
    secret: Annotated[str, typer.Option(prompt=True, hide_input=True)],
) -> None:
    """Store an encrypted provider key (BYOK). The secret is prompted, not echoed."""
    with _client() as client:
        resp = client.post(
            "/api/provider-keys",
            json={"provider": provider, "label": label, "secret": secret},
        )
    if resp.status_code >= 400:
        _fail(resp)
    console.print(f"[{LIME}]stored[/] {provider} key {resp.json()['id']}.")


@providers_app.command("list")
def providers_list() -> None:
    with _client() as client:
        resp = client.get("/api/provider-keys")
    if resp.status_code >= 400:
        _fail(resp)
    table = _table("PROVIDER KEYS", ["provider", "label", "created", "revoked"])
    for k in resp.json():
        table.add_row(
            k["provider"], k["label"], k["created_at"][:19], (k["revoked_at"] or "-")[:19]
        )
    console.print(table)


@providers_app.command("revoke")
def providers_revoke(key_id: str) -> None:
    with _client() as client:
        resp = client.post(f"/api/provider-keys/{key_id}/revoke")
    if resp.status_code >= 400:
        _fail(resp)
    console.print("revoked.")


# --- logs --------------------------------------------------------------------


@logs_app.command("list")
def logs_list(
    model: Annotated[str | None, typer.Option()] = None,
    since: Annotated[str | None, typer.Option(help="ISO timestamp.")] = None,
    limit: Annotated[int, typer.Option()] = 50,
) -> None:
    params: dict[str, str | int] = {"limit": limit}
    if model:
        params["model"] = model
    if since:
        params["since"] = since
    with _client() as client:
        resp = client.get("/api/requests", params=params)
    if resp.status_code >= 400:
        _fail(resp)
    table = _table(
        "SIGNAL / REQUESTS", ["created", "model", "status", "in", "out", "cost usd", "ms"]
    )
    for r in resp.json():
        cost = f"{r['cost_usd']:.6f}" if r["cost_usd"] is not None else "-"
        table.add_row(
            r["created_at"][:19], r["model"], str(r["status_code"] or r["error"] or "-"),
            str(r["input_tokens"] or "-"), str(r["output_tokens"] or "-"), cost,
            str(r["latency_ms"] or "-"),
        )
    console.print(table)


@logs_app.command("show")
def logs_show(request_id: str) -> None:
    with _client() as client:
        resp = client.get(f"/api/requests/{request_id}")
    if resp.status_code >= 400:
        _fail(resp)
    r = resp.json()
    console.print_json(data=r)


# --- cost --------------------------------------------------------------------


@cost_app.command("summary")
def cost_summary(
    group_by: Annotated[str, typer.Option(help="model or day")] = "model",
    since: Annotated[str | None, typer.Option(help="ISO timestamp.")] = None,
) -> None:
    params: dict[str, str | int] = {"group_by": group_by}
    if since:
        params["since"] = since
    with _client() as client:
        resp = client.get("/api/cost/summary", params=params)
    if resp.status_code >= 400:
        _fail(resp)
    table = _table(f"COST / BY {group_by.upper()}", [group_by, "requests", "cost usd"])
    total = 0.0
    for b in resp.json():
        total += b["cost_usd"]
        table.add_row(b["key"], str(b["requests"]), f"{b['cost_usd']:.6f}")
    console.print(table)
    console.print(f"[{CORAL}]total[/]  {total:.6f} usd")


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(app())  # pragma: no cover
