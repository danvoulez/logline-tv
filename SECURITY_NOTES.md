# Security Notes and Credential Hardening Path

## Current State

### Credentials Stored in Database
The acquisition subsystem stores credentials in the database for browser-based retrieval:

**Table: `domain_policies`**
- `login_url` - URL for login page
- `login_email_selector` - CSS selector for email input
- `login_password_selector` - CSS selector for password input
- `login_submit_selector` - CSS selector for submit button
- `login_success_selector` - CSS selector for successful login indicator
- `credential_email` - Email address for login
- `credential_password` - **Password stored in plaintext**

**Table: `candidate_assets`**
- No direct credentials, but may reference domain policies

### Configuration Secrets
The following secrets are configured via environment variables:

**Cloudflare R2 CDN**
- `CLOUDFLARE_ACCOUNT_ID` - Account identifier
- `CLOUDFLARE_R2_ACCESS_KEY` - Access key ID
- `CLOUDFLARE_R2_SECRET_KEY` - Secret access key
- `CLOUDFLARE_R2_PUBLIC_URL` - Public URL for CDN

**Admin Authentication**
- `ADMIN_TOKEN` - Token for admin API access (empty = no auth)

**External APIs**
- `PEXELS_API_KEY` - API key for Pexels video discovery

### Current Protections
1. `.env` is in `.gitignore` - local environment files not committed
2. `.env.example` documents expected variables without values
3. Pydantic schemas use `repr=False` on password field to prevent accidental logging
4. No hardcoded credentials in source code
5. Docker Compose uses environment variable injection

## Identified Risks

### High Risk
1. **Database plaintext passwords**: `domain_policies.credential_password` stored in plaintext
   - Impact: Database compromise exposes all third-party credentials
   - Current mitigation: None

### Medium Risk
2. **Environment variable exposure**: Secrets in env vars visible to:
   - Docker inspect
   - Process listing (in some configurations)
   - CI logs if not properly masked
   - Impact: Credential leakage through operational channels
   - Current mitigation: `.env` in gitignore

3. **No secret rotation**: No mechanism to rotate credentials without manual DB updates
   - Impact: Long-lived credentials increase exposure window
   - Current mitigation: None

### Low Risk
4. **Admin token in env var**: `ADMIN_TOKEN` stored in plaintext
   - Impact: Admin API access if leaked
   - Current mitigation: Can be left empty for no auth (dev mode)

## Recommended Hardening Path

### Phase 1: Immediate (No code changes)
1. **Document current state**: This file
2. **Operational procedures**:
   - Use separate `.env` files for each environment (dev, staging, prod)
   - Never commit `.env` files
   - Rotate credentials regularly
   - Use strong, unique passwords for each domain policy

### Phase 2: Database Encryption at Rest
1. **Add encryption library**:
   - Use `cryptography` or `sqlalchemy-utils` for field-level encryption
   - Add `EncryptedString` type for sensitive fields

2. **Encrypt credential fields**:
   ```python
   # In models.py
   from sqlalchemy_utils import EncryptedType
   from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine

   credential_password: Mapped[bytes] = mapped_column(
       LargeBinary,
       nullable=True
   )
   # Use application-level encryption/decryption
   ```

3. **Migration**:
   - Add migration to encrypt existing plaintext passwords
   - Back up database before migration
   - Test migration on staging first

### Phase 3: Secret Management Service
1. **Integrate secret manager**:
   - AWS Secrets Manager
   - HashiCorp Vault
   - Cloudflare Workers Secrets (if using Cloudflare)

2. **Update configuration**:
   - Remove secrets from environment variables
   - Fetch secrets at startup from secret manager
   - Cache secrets in memory with TTL

3. **Rotation support**:
   - Add API endpoint to trigger credential refresh
   - Support automatic rotation policies
   - Audit trail of credential access

### Phase 4: Admin Authentication Hardening
1. **Replace admin token with proper auth**:
   - JWT-based authentication
   - OAuth/OIDC integration
   - Session-based auth with secure cookies

2. **Rate limiting**:
   - Add rate limiting to admin endpoints
   - Implement brute force protection

3. **Audit logging**:
   - Log all admin actions with user identity
   - Store logs in immutable storage

### Phase 5: CI/CD Security
1. **GitHub Actions secrets**:
   - Use GitHub Actions secrets for CI credentials
   - Never log secrets in CI output
   - Use federated credentials for cloud providers

2. **Production deployment**:
   - Use sealed secrets for production
   - Implement secret injection at deployment time
   - Separate secrets per environment

## Operational Checklist

### Before Production Deployment
- [ ] All passwords in `domain_policies` are strong and unique
- [ ] `.env` file is not committed to repository
- [ ] `.env.example` is up to date
- [ ] CI/CD pipelines use secret management (not env vars in logs)
- [ ] Database backups are encrypted
- [ ] Database access is restricted (IP whitelisting, VPN)
- [ ] SSL/TLS enabled for all database connections
- [ ] Admin authentication is enabled (not empty ADMIN_TOKEN)
- [ ] Log aggregation excludes sensitive fields
- [ ] Secret rotation procedure documented and tested

### Monitoring
- [ ] Set up alerts for suspicious database access
- [ ] Monitor for credential leakage in logs
- [ ] Track admin API access patterns
- [ ] Audit secret access from secret manager

## Notes

- The acquisition subsystem's credential storage is designed for browser automation, not for API keys. The plaintext storage is a known limitation for the MVP.
- Cloudflare R2 credentials follow standard S3-compatible patterns and should be managed via Cloudflare's dashboard or API.
- For current lab/admission use, the plaintext credential storage is acceptable as the system is not production-hardened.
