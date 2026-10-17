# Security

**One credential.** The service holds one credential: the Google service-account key that it
writes the spreadsheet with (`google-sheets-sa`). The key contains a private key.
- It is a secret under `${STATE_DIR}/secrets` (file `0600`, directory `0700`). It is seeded and
  rotated only through tier2-project, and compose mounts it read-only at `/run/secrets`.
- It is never in Git, `config.yaml` or the image, and it is never logged.
- The client asks only for the `spreadsheets` scope, so the key can reach only the spreadsheets
  shared with the service account.
- How it is seeded and rotated: [operations.md](operations.md), "The Google service-account key".

**No mail credential.** Alerts are posted to tier-4-notify, which holds the mail credential
(devops-model#264).

**Network.** The service has no inbound ports. It calls out to Google's Sheets API, to Yahoo
Finance for prices (`yfinance`), and to tier-4-notify over the shared service network.
