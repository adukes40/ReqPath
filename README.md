# Procurement Workflow API

A lightweight, API-first procurement tracking system for managing requests, approvals, and documents.

## Features

- **Procurement Requests**: Create, track, and manage purchase requests
- **Line Items**: Track individual items with quantities, prices, and vendors
- **Document Management**: Upload and organize quotes, invoices, POs, receipts
- **Approval Workflow**: Built-in approval routing with audit trail
- **Reporting**: Spending analysis, vendor reports, pipeline aging
- **Export**: CSV and Excel export capabilities

## Tech Stack

- **FastAPI** - Modern, fast Python web framework
- **PostgreSQL** - Reliable relational database
- **SQLAlchemy** - Python ORM
- **Nginx** - Reverse proxy
- **Gunicorn** - Production WSGI server

## Quick Start (Docker)

```bash
# Clone the repository
git clone https://github.com/your-org/procurement-api.git
cd procurement-api

# Start with Docker Compose
docker-compose up -d

# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

## LXC Deployment (Proxmox)

### 1. Create LXC Container

In Proxmox:
- Create CT (Container)
- Template: `ubuntu-24.04-standard`
- Hostname: `procurement-api`
- CPU: 2 cores
- Memory: 2048 MB
- Disk: 20 GB
- Network: DHCP or static IP

### 2. Prepare Container

```bash
# SSH into the container
ssh root@<container-ip>

# Update and install git
apt update && apt install -y git
```

### 3. Clone and Setup

```bash
# Clone repository
git clone https://github.com/your-org/procurement-api.git /tmp/procurement-api

# Run setup script
chmod +x /tmp/procurement-api/lxc-setup.sh
/tmp/procurement-api/lxc-setup.sh

# Copy application code
cp -r /tmp/procurement-api/app /opt/procurement-api/

# Start the service
systemctl start procurement-api
```

### 4. Verify Installation

```bash
# Check service status
systemctl status procurement-api

# Check logs
journalctl -u procurement-api -f

# Test API
curl http://localhost/health
```

## API Authentication

All endpoints require an API key. Pass it via:

- **Header**: `X-API-Key: your-api-key`
- **Query Parameter**: `?api_key=your-api-key`

### Getting an API Key

1. Use the admin API key generated during setup
2. Create a user via API to get a user-specific key

```bash
# Create a user (using admin key)
curl -X POST http://localhost/api/v1/users \
  -H "X-API-Key: admin-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@district.edu",
    "name": "John Doe",
    "department": "Technology",
    "role": "requester"
  }'
```

## API Endpoints

### Requests
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/requests` | List all requests |
| POST | `/api/v1/requests` | Create new request |
| GET | `/api/v1/requests/{id}` | Get request details |
| PATCH | `/api/v1/requests/{id}` | Update request |
| DELETE | `/api/v1/requests/{id}` | Delete draft request |
| POST | `/api/v1/requests/{id}/submit` | Submit for approval |
| POST | `/api/v1/requests/{id}/status` | Update status |

### Line Items
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/requests/{id}/items` | List items |
| POST | `/api/v1/requests/{id}/items` | Add item |
| PATCH | `/api/v1/requests/{id}/items/{item_id}` | Update item |
| DELETE | `/api/v1/requests/{id}/items/{item_id}` | Remove item |

### Documents
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/requests/{id}/documents` | List documents |
| POST | `/api/v1/requests/{id}/documents` | Upload document |
| GET | `/api/v1/documents/{id}/download` | Download file |
| DELETE | `/api/v1/requests/{id}/documents/{doc_id}` | Delete document |

### Approvals
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/requests/{id}/approve` | Approve request |
| POST | `/api/v1/requests/{id}/reject` | Reject request |
| GET | `/api/v1/approvals/pending` | My pending approvals |

### Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/reports/spending/by-month` | Monthly spending |
| GET | `/api/v1/reports/spending/by-department` | Department spending |
| GET | `/api/v1/reports/vendors` | Vendor analysis |
| GET | `/api/v1/reports/status` | Pipeline status |
| GET | `/api/v1/reports/export/requests` | Export to CSV/Excel |

## Example Usage

### Create a Request

```bash
curl -X POST http://localhost/api/v1/requests \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Classroom Chromebooks",
    "description": "30 Chromebooks for new computer lab",
    "department": "Technology",
    "priority": "high",
    "needed_by": "2025-03-01",
    "line_items": [
      {
        "description": "Lenovo 300e Chromebook Gen 3",
        "quantity": 30,
        "unit_price": 299.00,
        "vendor": "CDW-G",
        "category": "Hardware"
      }
    ]
  }'
```

### Upload a Quote

```bash
curl -X POST http://localhost/api/v1/requests/1/documents \
  -H "X-API-Key: your-api-key" \
  -F "file=@quote.pdf" \
  -F "doc_type=quote" \
  -F "description=CDW-G Quote #12345"
```

### Get Spending Report

```bash
curl "http://localhost/api/v1/reports/spending/by-month?year=2025" \
  -H "X-API-Key: your-api-key"
```

## Status Flow

```
DRAFT → PENDING → APPROVED → ORDERED → RECEIVED → COMPLETE
                ↘ REJECTED
```

## Configuration

Environment variables (in `.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `SECRET_KEY` | JWT signing key | - |
| `API_KEYS` | Comma-separated admin keys | - |
| `UPLOAD_DIR` | Document storage path | `./uploads` |
| `MAX_UPLOAD_SIZE_MB` | Max file size | `25` |
| `ALLOWED_EXTENSIONS` | Allowed file types | `pdf,doc,docx,...` |

## Backup

### Database
```bash
# Backup
pg_dump -U procurement procurement > backup.sql

# Restore
psql -U procurement procurement < backup.sql
```

### Files
```bash
# Backup uploads
tar -czf uploads-backup.tar.gz /opt/procurement-api/uploads/
```

## Troubleshooting

### Service won't start
```bash
# Check logs
journalctl -u procurement-api -n 50

# Check config
cat /opt/procurement-api/.env

# Test manually
cd /opt/procurement-api
source venv/bin/activate
python -m app.main
```

### Database connection issues
```bash
# Test PostgreSQL
sudo -u postgres psql -c "SELECT 1"

# Check pg_hba.conf if needed
nano /etc/postgresql/16/main/pg_hba.conf
```

## License

MIT
