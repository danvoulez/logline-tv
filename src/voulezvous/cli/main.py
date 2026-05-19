import asyncio
from datetime import date

import click

from voulezvous.logging_config import setup_logging


@click.group()
def cli():
    """Voulezvous streaming engine CLI."""
    setup_logging()


@cli.command("seed-demo-data")
def seed_demo_data_cmd():
    """Load demo assets into the database."""
    asyncio.run(_seed())


async def _seed():
    from voulezvous.database import async_session
    from voulezvous.services.seed import seed_demo_data

    async with async_session() as db:
        result = await seed_demo_data(db)
        click.echo(f"Seeded: {result}")


@cli.command("api")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8000, type=int)
def run_api(host: str, port: int):
    """Run the FastAPI server."""
    import uvicorn

    uvicorn.run("voulezvous.api.app:app", host=host, port=port, reload=False)


@cli.command("planner")
@click.option("--date", "plan_date", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--hours", default=24, type=int)
@click.option("--mix-music", is_flag=True, default=False)
def planner_cmd(plan_date, hours: int, mix_music: bool):
    """Generate a stream plan for a date."""
    d = plan_date.date() if hasattr(plan_date, "date") else plan_date
    asyncio.run(_generate_plan(d, hours, mix_music))


async def _generate_plan(plan_date: date, hours: int, mix_music: bool):
    from voulezvous.database import async_session
    from voulezvous.services.planner import generate_plan

    async with async_session() as db:
        plan = await generate_plan(db, plan_date, hours, mix_music)
        click.echo(f"Plan {plan.id} created for {plan_date} with {len(plan.items)} items")


@cli.command("prep-worker")
@click.option("--once", is_flag=True, default=False, help="Run one cycle then exit")
@click.option("--interval", default=30, type=int, help="Poll interval in seconds")
def prep_worker_cmd(once: bool, interval: int):
    """Run the preparation worker."""
    asyncio.run(_prep_worker(once, interval))


async def _prep_worker(once: bool, interval: int):
    from voulezvous.database import async_session
    from voulezvous.services.prep_worker import run_prep_cycle

    while True:
        async with async_session() as db:
            processed = await run_prep_cycle(db)
            click.echo(f"Prep cycle: processed {processed} items")
        if once:
            break
        await asyncio.sleep(interval)


@cli.command("streamer")
def streamer_cmd():
    """Run the streamer process."""
    asyncio.run(_streamer())


async def _streamer():
    from voulezvous.services.streamer import run_streamer

    await run_streamer()


@cli.command("reporter")
@click.option("--date", "report_date", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
def reporter_cmd(report_date):
    """Generate a daily report."""
    asyncio.run(_reporter(report_date.date() if hasattr(report_date, "date") else report_date))


async def _reporter(report_date: date):
    from voulezvous.database import async_session
    from voulezvous.services.reporter import generate_daily_report

    async with async_session() as db:
        report = await generate_daily_report(db, report_date)
        click.echo(report.markdown_text)


if __name__ == "__main__":
    cli()
