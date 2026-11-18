# Enterprise secrets with 1Password CLI

A small order service needs a different set of credentials in `test`, `dev`,
`staging`, and `prod`. Each stage has the same four inputs:

| Variable | What the service uses it for |
| --- | --- |
| `DATABASE_DSN` | PostgreSQL connection URL containing the username and password |
| `SENTRY_DSN` | Sentry ingest destination for the stage's project |
| `SLACK_BOT_TOKEN` | Bearer token for the order notifications bot |
| `GOOGLE_MAPS_API_KEY` | API key for calculating delivery routes |

Each bundle also has `CONFIG_STAGE`, a nonsecret label. The app checks this
against the stage you requested before it prepares any requests. A Sentry DSN
identifies the ingest destination and is distinct from a
[Sentry API token](https://docs.sentry.io/api/auth/).

The `prod` database fixture has this shape:

```dotenv
DATABASE_DSN=postgres://<username>:<password>@my-prod-host.us-east-2.rds.amazonaws.com:5432/data
```

The generator gives each stage synthetic values and percent-encodes reserved
characters in the database password. The app checks both DSN formats and
constructs Slack and Google Maps requests in memory. It opens no database or
network connections. It prints field names for configuration errors and never
logs the values, request headers, or parsed DSNs.

## Prerequisites

Run the commands from the `op-cli-demo` directory in Bash or Zsh. You need
Python 3.10 or newer and [1Password CLI](https://www.1password.dev/cli/get-started)
2.42 or newer for this walkthrough. There are no Python dependencies to install.

```sh
python3 --version
op --version
```

Sign in to the 1Password desktop app and unlock it. On macOS, enable
**Settings → Developer → Integrate with 1Password CLI**, then run
`op vault list` and approve the desktop prompt to authorize your terminal.

## Option A: 1Password Environments

Start here if you want 1Password to supply environment variables directly to the
app. Create and populate each Environment in the desktop app, then pass its ID
to `op run`. The `.env.example` and JSON templates belong to Option B.

### 1. Create the dev Environment

In the 1Password desktop app, open **Developer → View Environments → New
environment**. Name it `enterprise-orders-dev`, choose the appropriate account
if prompted, and select **Save**. If **View Environments** is missing on a
managed account, ask your 1Password administrator to check the
[Environments policy](https://www.1password.dev/environments#turn-the-environments-policy-on-or-off).

### 2. Import synthetic values

Run this in your terminal. It creates a private temporary file with the four
synthetic values and `CONFIG_STAGE=dev` and prints where to find it.

```sh
stage=dev
if import_dir=$(mktemp -d); then
  import_file="$import_dir/enterprise-orders-$stage.env"
  (umask 077; python3 seed_demo.py "$stage" --format dotenv > "$import_file") &&
    printf 'Open folder: %s\nSelect file: %s\n' "$import_dir" "${import_file##*/}"
fi
```

Open `enterprise-orders-dev` and select **Import .env file**. On macOS, press
**⌘⇧G** in the file picker, paste the printed folder path, and select
`enterprise-orders-dev.env`. After importing, check that the four names from the
table above and `CONFIG_STAGE` appear in the Environment. You can also enter
the values individually with **New secret**.
Once the import is complete, remove the temporary file from the same terminal:

```sh
rm -f "$import_file" && rmdir "$import_dir"
```

### 3. Copy the ID and run the demo

In `enterprise-orders-dev`, select **Manage environment → Copy environment ID**.
Replace `PASTE_DEV_ENVIRONMENT_ID` below with the copied ID. Approve the 1Password
prompt if one appears.

```sh
dev_environment_id='PASTE_DEV_ENVIRONMENT_ID'
op run --environment "$dev_environment_id" -- python3 app.py --stage dev
```

Expected output:

```text
Stage: DEV
PostgreSQL and Sentry DSNs: validated
Slack and Google Maps: credential headers prepared
No connections opened or credentials logged.
```

The Environment ID tells `op` which values to inject. The demo's `--stage`
argument tells Python which `CONFIG_STAGE` to expect. `op run` supplies the
values to the launched process, where the app reads them with `os.environ`.
[Run command reference](https://www.1password.dev/cli/reference/commands/run)

### 4. Switch stages

Repeat steps 1 and 2 for `test`, `staging`, or `prod`. Use the matching name
(`enterprise-orders-staging`, for example) and change `stage` in the import
command so the file contains values for that stage. Copy the new Environment's
ID and pass the matching `--stage`:

```sh
staging_environment_id='PASTE_STAGING_ENVIRONMENT_ID'
op run --environment "$staging_environment_id" -- python3 app.py --stage staging
```

The first line should be `Stage: STAGING`. Passing `--stage dev` with that same
ID should report a stage mismatch before the app prepares requests. The stage
check catches a configuration mistake. Environment permissions control who can
retrieve the values.

### Use this pattern in your own project

1. List the variable names your app already reads, such as `DATABASE_URL` or
   `SLACK_BOT_TOKEN`. Use those exact names in every Environment. Store the
   values for each stage in its own Environment. For a database URL, percent
   encode reserved characters in the username and password before building it.
2. Keep the app's existing entry point and wrap its usual command with
   `op run`. For example, set `OP_ENVIRONMENT_ID` to your project's dev
   Environment ID and launch a Node project with:

   ```sh
   op run --environment "$OP_ENVIRONMENT_ID" -- npm run dev
   ```

   Let injected variables take precedence if your framework also loads a local
   `.env`. Keep ordinary defaults in your normal project configuration and
   store live credentials in 1Password.
3. For CI, configure the Environment ID as a deployment variable and store
   `OP_SERVICE_ACCOUNT_TOKEN` in the CI provider's secret store. Give each job a
   [service account scoped to its stage's Environment](https://www.1password.dev/environments/read-environment-variables).
   Use the same `op run` wrapper around the build, test, or deploy command that
   needs the credentials. Keep production access out of developer and test jobs.
4. Rotate a credential in the provider and update the matching value in
   1Password. The next launch fetches the updated value. Restart any processes
   that still hold the old value.

## Option B: Grouped vault items for `.env` and JSON

This path works with standard vault items. It uses one Secure Note per stage,
with **deployment**, **database**, **observability**, and **integrations**
sections. Both config templates reference the same field names. Pick the stage
with `APP_ENV`.

### Seed a demo vault

Set `OP_DEMO_VAULT` to a vault name or ID. The loop creates only missing demo
items and leaves existing values in place. The generator writes directly to
`op item create` over stdin.

```sh
export OP_DEMO_VAULT='Private'
```

For a fresh setup, use the following from Bash or Zsh:

```sh
(
  set -o pipefail
  existing=$(op item list --vault "$OP_DEMO_VAULT" --format=json |
    python3 -c 'import json, sys; print("\n".join(item["title"] for item in json.load(sys.stdin)))') || exit 1
  for stage in test dev staging prod; do
    if grep -Fxq -- "enterprise-orders-$stage" <<< "$existing"; then
      continue
    fi
    python3 seed_demo.py "$stage" --format item |
      op item create --vault "$OP_DEMO_VAULT" - >/dev/null || exit 1
  done
)
```

Prepare your local templates if they aren't already configured:

```sh
cp -n .env.example .env
cp -n config.example.json config.local.json
```

The templates contain references such as
`op://$OP_DEMO_VAULT/enterprise-orders-$APP_ENV/database/dsn`. If the local
copies already contain a vault ID, they use that ID instead. For a real
deployment, use a separate vault for each stage and set `OP_DEMO_VAULT` to the
appropriate vault at launch. Four items in one demo vault show organization;
they share the vault's access permissions.

### Run with `.env`

```sh
stage=dev
APP_ENV="$stage" op run --env-file=.env -- python3 app.py --stage "$stage"
```

`op run` supplies the values to the Python process. The file stays a reference
template. See [environment variable injection](https://www.1password.dev/cli/secrets-environment-variables).

### Run with JSON

```sh
stage=staging
(
  set -o pipefail
  APP_ENV="$stage" op inject --in-file=config.local.json |
    python3 app.py --stage "$stage" --config -
)
```

Keep the pipe connected. `op inject` sends plaintext JSON to stdout, and the
pipe gives it directly to the app. If a tool needs a physical file, use
`op inject --out-file` with mode `0600` in a private temporary directory and
delete the file after the command. The generator's values are safe to insert
into JSON strings. Arbitrary real values may need JSON escaping. See the
[config template documentation](https://www.1password.dev/cli/secrets-config-files).

Both vault commands produce the same status output as the native Environment
commands, with the selected stage on the first line.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `unknown flag: --environment` | Run `op --version` and update the CLI on your PATH. |
| Environment cannot be found or accessed | Copy the ID again from **Manage environment** and check that the signed-in account has access. |
| `Missing DATABASE_DSN` or another variable | Check the exact variable name and confirm it has a value in the selected Environment. |
| Unresolved reference in the native Environment path | Populate the Environment using the generated import or enter values in the desktop app. The vault templates in this repo contain references for Option B. |
| Stage mismatch | Match the stage embedded in the imported file (`CONFIG_STAGE`) to the demo's `--stage` argument. |

If macOS blocks the desktop connection, check **System Settings → General →
Login Items & Extensions → App Background Activity** for 1Password. Quit and
reopen the app after allowing it, then retry `op vault list`. See the
[1Password troubleshooting guide](https://www.1password.dev/cli/app-integration#troubleshooting).

## Notes on handling credentials

Use synthetic values with coding agents. `op run` masks output by default, but
code receiving a secret can still write it to files, logs, or network requests.
Keep production vault or Environment access outside development sessions.
