# Operations

The service runs once a night on jarvis: the Tier-1 kicker job
`ai.calumlabs.kicker.investment-reviews.nightly` runs `docker compose run --rm runner` at 22:05
Europe/London (`deploy/service.yaml`, `schedules`). Its exit codes and metrics are described in
`deploy/entrypoints/run-once.sh`.

## The Google service-account key

The nightly run writes the spreadsheet as a Google Cloud service account. Its key is the
credential `google-sheets-sa` (devops-model `registers/identities.md`, "Credential lifecycle").

**Where it lives.**
- On jarvis: `/Users/cl/srv/investment-reviews/state/secrets/google_sheets_service_account.json`,
  mode `0600` in a `0700` directory (SDI, "Secrets").
- It is declared in `deploy/service.yaml` under `secrets:`, and mounted by compose at
  `/run/secrets/google_sheets_service_account.json`, where `google_sheets_client.py` reads it.
- It is not in `config.yaml`. A `google_sheets.credentials_path` left there is ignored, and the run
  logs a warning naming it.
- For a run outside the container, set `GOOGLE_SHEETS_CREDENTIALS_FILE` to the key's path.

Before devops-model#333 the key was in `state/credentials/`, outside `secrets/`, so tier2-project
could neither seed nor rotate it.

**If the file is missing,** compose cannot create the container ("bind source path does not
exist"), and the nightly job fails. A deploy still succeeds, because it only builds the image. The
health metric goes stale after 36 hours.

**Seeding it** on a new host or after a loss. Run on jarvis, with a copy of the key in a file only
you can read:

```sh
tier2-project register-service investment-reviews jarvis \
  --seed-secret-file <key file> --seed-secret-name google_sheets_service_account.json
```

Then delete the copy.

**Rotating it.** Rotate after a leak, or whenever Google's key policy calls for it. The key does
not expire.
1. In the Google Cloud console, open IAM & Admin → Service accounts. Choose the account whose email
   is the key's `client_email`, then Keys → Add key → Create new key → JSON. The new key is
   downloaded.
2. On jarvis, replace the secret, then delete the downloaded file:
   ```sh
   tier2-project rotate-secret investment-reviews google_sheets_service_account.json \
     --seed-secret-file <new key file>
   ```
   The file is written in place. The next nightly run reads it, and nothing needs restarting
   (SDI, "Rotation").
3. Check that the new key works. This reads the sheet's headers and row count and changes
   nothing:
   ```sh
   export PATH=/usr/bin:/bin:/usr/sbin:/opt/homebrew/bin
   cd /Users/cl/srv/investment-reviews/current/deploy
   STATE_DIR=/Users/cl/srv/investment-reviews/state docker compose \
     --env-file /Users/cl/srv/investment-reviews/state/env/deploy.env --profile manual \
     run --rm --entrypoint python runner /app/google_sheets_client.py test --config /run/config/config.yaml
   ```
4. In the console, delete the old key from the same Keys list (the older of the two). Until you
   do, the old key still works.
