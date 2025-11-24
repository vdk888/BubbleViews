# Secret Management Runbook

## Overview

This runbook documents how secrets are managed in the Reddit AI Agent application. Proper secret management is critical for security - compromised secrets can lead to unauthorized access, data breaches, or service disruption.

## Table of Contents

1. [Secret Types](#secret-types)
2. [Generating Secrets](#generating-secrets)
3. [Where Secrets Are Stored](#where-secrets-are-stored)
4. [Secret Rotation Policy](#secret-rotation-policy)
5. [Updating Secrets Without Downtime](#updating-secrets-without-downtime)
6. [Emergency Procedures](#emergency-procedures)
7. [Security Best Practices](#security-best-practices)

---

## Secret Types

The application uses the following types of secrets:

| Secret | Purpose | Rotation Frequency | Criticality |
|--------|---------|-------------------|-------------|
| `SECRET_KEY` | JWT token signing | Every 90 days | **CRITICAL** |
| `REDDIT_CLIENT_SECRET` | Reddit API authentication | When compromised | **HIGH** |
| `REDDIT_PASSWORD` | Reddit account access | Every 180 days | **HIGH** |
| `OPENROUTER_API_KEY` | LLM API access | When compromised | **HIGH** |

---

## Generating Secrets

### JWT Secret Key

The `SECRET_KEY` is used to sign JWT tokens for API authentication. It must be:
- At least 32 characters long
- Cryptographically random
- Never committed to version control

**Generate a new secret key:**

```bash
# Using OpenSSL (recommended)
openssl rand -hex 32

# Using Python
python3 -c "import secrets; print(secrets.token_hex(32))"

# Using /dev/urandom (Linux/macOS)
head -c 32 /dev/urandom | xxd -p -c 64
```

**Example output:**
```
a7f3b2c9d8e1f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9
```

### Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Create a new app (script type)
3. Note the `client_id` and `client_secret`
4. Keep these values secure - they provide full access to your Reddit account

### OpenRouter API Key

1. Log in to https://openrouter.ai/
2. Navigate to API Keys section
3. Generate a new API key
4. Set spending limits to prevent unexpected charges

---

## Where Secrets Are Stored

### Development Environment

**Local `.env` file** (gitignored):
```bash
# backend/.env
SECRET_KEY=<generated-with-openssl>
REDDIT_CLIENT_SECRET=<from-reddit-apps>
REDDIT_PASSWORD=<your-reddit-password>
OPENROUTER_API_KEY=<from-openrouter>
```

**Security measures:**
- `.env` is listed in `.gitignore` - never commit it
- Use `.env.example` as a template (no real secrets)
- File permissions: `chmod 600 .env` (owner read/write only)

### Production Environment

**Environment Variables** (recommended for production):

Set secrets directly in the environment:

```bash
# Using systemd service file
Environment="SECRET_KEY=<secret>"
Environment="REDDIT_CLIENT_SECRET=<secret>"

# Or using systemd drop-in file
sudo systemctl edit reddit-agent
# Add secrets in the override file
```

**DigitalOcean droplet setup:**

```bash
# Create secure .env file on server
sudo nano /opt/reddit-agent/backend/.env

# Set restrictive permissions
sudo chown reddit-agent:reddit-agent /opt/reddit-agent/backend/.env
sudo chmod 600 /opt/reddit-agent/backend/.env

# Verify permissions
ls -la /opt/reddit-agent/backend/.env
# Expected: -rw------- (600)
```

### Secret Storage Hierarchy

```
Priority (highest to lowest):
1. Environment variables (set in shell/systemd)
2. .env file in backend/ directory
3. .env file in parent directory
4. Default values (only for non-sensitive settings)
```

**Never:**
- Commit secrets to Git
- Store secrets in code files
- Share secrets via Slack/email/chat
- Log secrets in application logs

---

## Secret Rotation Policy

### Scheduled Rotation

| Secret | Rotation Schedule | Reason |
|--------|------------------|---------|
| `SECRET_KEY` | Every 90 days | Best practice for JWT signing keys |
| `REDDIT_PASSWORD` | Every 180 days | Reddit account security |
| `OPENROUTER_API_KEY` | Annually or when needed | Cost control + security |
| `REDDIT_CLIENT_SECRET` | When compromised | Only if leaked or suspicious activity |

### Rotation Calendar

Set reminders using:
```bash
# Add to crontab for monthly reminder
0 9 1 * * echo "Check if secrets need rotation" | mail -s "Secret Rotation Reminder" admin@yourdomain.com
```

---

## Updating Secrets Without Downtime

### Zero-Downtime Secret Rotation

The application supports graceful secret updates using a rolling restart strategy.

#### Step 1: Update Secret in Environment

**Development:**
```bash
# Edit .env file
nano backend/.env

# Update the secret
SECRET_KEY=<new-secret-key>
```

**Production (systemd):**
```bash
# Edit environment file
sudo nano /opt/reddit-agent/backend/.env

# Update the secret
SECRET_KEY=<new-secret-key>
```

#### Step 2: Reload Application

**Development:**
```bash
# Restart the server (Ctrl+C and restart)
make run
```

**Production:**
```bash
# Reload systemd configuration (if using systemd environment)
sudo systemctl daemon-reload

# Restart service gracefully
sudo systemctl restart reddit-agent

# Verify service is running
sudo systemctl status reddit-agent
```

#### Step 3: Verify Changes

```bash
# Check logs for successful startup
journalctl -u reddit-agent -n 50 --no-pager

# Test API health endpoint
curl -X GET http://localhost:8000/health

# Test authentication with new secret (if rotating SECRET_KEY)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
```

### Rotating JWT Secret Key (SECRET_KEY)

**Important:** Rotating `SECRET_KEY` will invalidate all existing JWT tokens.

**Procedure:**
1. **Notify users** (if applicable) that they'll need to re-authenticate
2. **Generate new key:**
   ```bash
   NEW_KEY=$(openssl rand -hex 32)
   echo $NEW_KEY  # Save this temporarily
   ```
3. **Update `.env`:**
   ```bash
   SECRET_KEY=$NEW_KEY
   ```
4. **Restart application**
5. **Verify** users can log in and get new tokens
6. **Clean up** - securely delete old key from notes

**Migration strategy (advanced):**
For zero-downtime rotation with dual-key validation, modify `security.py` to accept both old and new keys temporarily:

```python
# Pseudo-code for dual-key validation
def decode_token(token: str) -> Optional[TokenData]:
    try:
        return jwt.decode(token, NEW_KEY, algorithms=[ALGORITHM])
    except JWTError:
        # Fallback to old key
        return jwt.decode(token, OLD_KEY, algorithms=[ALGORITHM])
```

---

## Emergency Procedures

### Secret Compromised (Leaked/Exposed)

**Immediate Actions (within 15 minutes):**

1. **Revoke the compromised secret immediately**
   ```bash
   # For Reddit API
   - Go to https://www.reddit.com/prefs/apps
   - Delete the compromised app
   - Create a new app with new credentials

   # For OpenRouter
   - Log in to OpenRouter dashboard
   - Revoke compromised API key
   - Generate new API key
   ```

2. **Update application with new secret**
   ```bash
   # SSH to production server
   ssh user@your-droplet-ip

   # Update .env with new secret
   sudo nano /opt/reddit-agent/backend/.env

   # Restart service immediately
   sudo systemctl restart reddit-agent
   ```

3. **Verify service recovery**
   ```bash
   # Check logs
   sudo journalctl -u reddit-agent -n 100 --no-pager

   # Test API
   curl -X GET http://localhost:8000/health
   ```

4. **Investigate the leak**
   - Check Git history: `git log -p --all -S 'SECRET_KEY'`
   - Review application logs for unauthorized access
   - Check commit history on GitHub/GitLab
   - Scan codebase: `grep -r "SECRET_KEY" .`

5. **Document the incident**
   - What was compromised?
   - When was it discovered?
   - What actions were taken?
   - Root cause analysis

### If SECRET_KEY is Compromised

**Critical - All user sessions are potentially hijacked**

```bash
# 1. Generate new key immediately
NEW_SECRET=$(openssl rand -hex 32)

# 2. Update production .env
echo "SECRET_KEY=$NEW_SECRET" | sudo tee -a /opt/reddit-agent/backend/.env

# 3. Restart service (invalidates all tokens)
sudo systemctl restart reddit-agent

# 4. Force all users to re-authenticate
# (happens automatically when old tokens are rejected)

# 5. Monitor logs for suspicious activity
sudo journalctl -u reddit-agent -f | grep "401\|403\|Unauthorized"
```

### If Reddit Credentials are Compromised

```bash
# 1. Change Reddit password immediately
# - Go to Reddit account settings
# - Update password

# 2. Revoke OAuth app
# - Delete app at https://www.reddit.com/prefs/apps
# - Create new app

# 3. Update .env with new credentials
sudo nano /opt/reddit-agent/backend/.env

# 4. Restart service
sudo systemctl restart reddit-agent

# 5. Check for unauthorized posts/comments
# - Review Reddit account history
# - Delete any malicious content
```

### If OpenRouter API Key is Compromised

```bash
# 1. Revoke key in OpenRouter dashboard
# - Log in to https://openrouter.ai/
# - Revoke compromised key

# 2. Check usage/billing
# - Review unexpected API calls
# - Check for unusual spending patterns

# 3. Generate new key with spending limits
# - Set daily/monthly spend cap

# 4. Update .env
sudo nano /opt/reddit-agent/backend/.env

# 5. Restart service
sudo systemctl restart reddit-agent
```

---

## Security Best Practices

### Development

✅ **DO:**
- Use `.env` files for local secrets (gitignored)
- Use `.env.example` as template (no real values)
- Generate unique secrets for each environment
- Keep secrets out of code and logs
- Use environment variable validation (`config.py` checks)

❌ **DON'T:**
- Commit `.env` files to Git
- Share secrets via chat/email
- Use the same secrets across dev/staging/prod
- Log secret values in application logs
- Store secrets in plaintext notes

### Production

✅ **DO:**
- Use environment variables or encrypted secret stores
- Set restrictive file permissions (`chmod 600`)
- Rotate secrets on schedule
- Monitor access logs for anomalies
- Use separate secrets per environment
- Document all secret locations

❌ **DON'T:**
- Store secrets in database (except hashed passwords)
- Use default/example secrets in production
- Share production secrets with developers
- Store secrets in version control
- Use weak secrets (short, predictable)

### Secret Checklist

Before deploying to production:

- [ ] All secrets generated using cryptographically secure methods
- [ ] `.env` file permissions set to 600
- [ ] `.env` listed in `.gitignore`
- [ ] No secrets committed to Git history
- [ ] Secrets different from development environment
- [ ] Secret rotation calendar configured
- [ ] Backup secrets stored securely (encrypted password manager)
- [ ] Team knows emergency procedures
- [ ] Monitoring alerts configured for auth failures

### Verifying Secrets are Not in Git

```bash
# Check current files
git ls-files | xargs grep -l "sk-or-v1"
git ls-files | xargs grep -l "SECRET_KEY"

# Check entire Git history (slower)
git log -p --all -S 'SECRET_KEY'
git log -p --all -S 'sk-or-v1'

# If secrets found in history, remove them:
# WARNING: This rewrites Git history
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch backend/.env" \
  --prune-empty --tag-name-filter cat -- --all
```

---

## Monitoring and Alerts

### Signs of Compromised Secrets

Watch for:
- Unexpected API usage spikes
- Failed authentication attempts from unknown IPs
- Unusual Reddit posts/comments
- Unexpected LLM API costs
- 401/403 errors in logs

### Recommended Alerts

```bash
# Monitor failed auth attempts
sudo journalctl -u reddit-agent -f | grep "401" --line-buffered

# Monitor OpenRouter API costs
# Set up billing alerts in OpenRouter dashboard

# Monitor Reddit activity
# Check Reddit account regularly for unauthorized posts
```

---

## Testing Secret Configuration

### Verify Secrets are Loaded Correctly

```python
# backend/tests/test_secrets.py
import pytest
from app.core.config import settings

def test_secret_key_is_set():
    """Ensure SECRET_KEY is not placeholder value"""
    assert settings.secret_key != "generate-with-openssl-rand-hex-32"
    assert len(settings.secret_key) >= 32

def test_reddit_credentials_present():
    """Ensure Reddit credentials are configured"""
    assert settings.reddit_client_id
    assert settings.reddit_client_secret
    assert settings.reddit_username

def test_openrouter_key_present():
    """Ensure OpenRouter API key is configured"""
    assert settings.openrouter_api_key
    assert settings.openrouter_api_key.startswith("sk-")
```

Run tests:
```bash
cd backend
pytest tests/test_secrets.py -v
```

---

## Support and Questions

If you have questions about secret management:

1. **Check this runbook first**
2. **Review `.env.example`** for required secrets
3. **Check application logs** for configuration errors
4. **Contact team lead** for production secret access

**Remember:** When in doubt, rotate the secret. Better safe than sorry.
