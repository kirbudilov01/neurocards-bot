# Telegram Bot

This is a Telegram bot that uses `aiogram` and Supabase.

## Environment Variables

The following environment variables are required:

- `BOT_TOKEN`: Your Telegram bot token.
- `SUPABASE_URL`: The URL of your Supabase project.
- `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role key.
- `PUBLIC_BASE_URL`: The public URL of your application, used for setting the webhook.
- `WEBHOOK_SECRET_TOKEN`: An optional secret token used to secure your webhook.

## Database Migrations

To apply database migrations, navigate to the Supabase SQL editor and execute the contents of the migration files located in the `supabase/migrations` directory.

- `20240723120000_add_unique_index_on_tg_user_id.sql`
