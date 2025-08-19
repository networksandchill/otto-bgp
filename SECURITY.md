# Security Notice

### Testing Data:
- Use `test_devices.csv` for all testing purposes
- Contains safe RFC 1918 private IPs and localhost

### Security Requirements:

1. **SSH Credentials**: 
   - NEVER commit SSH usernames/passwords to git
   - Use environment variables: `SSH_USERNAME`, `SSH_PASSWORD`
   - Production: Use SSH keys instead of passwords

2. **Network Devices**:
   - Do not commit production IP addresses
   - Use mock/test IPs for development
   - Validate all CSV files before commits

3. **BGP Toolkit Usage**:
   ```bash
   # SAFE - Uses test devices
   bgp-toolkit collect test_devices.csv
   
   # UNSAFE - Do not use production IPs
   # bgp-toolkit collect production_devices.csv
   ```

### Git History Note:
The production IPs may still exist in git history. Consider:
- Repository cleanup if sensitive
- New repository for clean start
- .gitignore for future device lists

## Credential Management

**Development**: Environment variables
```bash
export SSH_USERNAME="test_user"
export SSH_PASSWORD="test_password"
```

**Production**: SSH key authentication
```bash
export SSH_USERNAME="bgp-service"
export SSH_KEY_PATH="/etc/ssh/bgp-toolkit/id_rsa"

```
