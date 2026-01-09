# Telegram Bot

This is a Telegram bot that uses `aiogram` and Supabase.

## Environment Variables

The following environment variables are required:

- `BOT_TOKEN`: Your Telegram bot token.
- `SUPABASE_URL`: The URL of your Supabase project.
- `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role key.
- `PUBLIC_BASE_URL`: The public URL of your application, used for setting the webhook.
- `WEBHOOK_SECRET_TOKEN`: An optional secret token used to secure your webhook.
- `LOG_LEVEL`: The logging level for the application (e.g., `DEBUG`, `INFO`, `WARNING`, `ERROR`). Defaults to `INFO`.
- `SENTRY_DSN`: An optional DSN for Sentry error reporting.
- `WORKER_ID`: An optional ID for the worker instance. Defaults to `default-worker`.

## Debugging

To debug the application, you can view the structured logs produced by the web service and the worker. On Render, these logs can be viewed in the "Logs" tab of your service.

You can search for the following fields in your logs to trace requests and diagnose issues:

- `tg_user_id`: The Telegram user ID.
- `job_id`: The ID of the generation job.
- `kie_task_id`: The ID of the KIE task.
- `worker_id`: The ID of the worker that processed the job.
