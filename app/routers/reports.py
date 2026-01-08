"""
Reports Router - Analytics and reporting endpoints
"""
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from io import BytesIO

from app.database import get_db
from app.models import ProcurementRequest, LineItem, User
from app.schemas import SpendingReport, VendorReport, StatusReport
from app.services.auth import get_current_user

router = APIRouter(prefix="/reports", tags=["Reports"])


# =============================================================================
# SPENDING REPORTS
# =============================================================================

@router.get("/spending/by-month", response_model=List[SpendingReport])
async def spending_by_month(
    year: int = Query(default_factory=lambda: datetime.now().year),
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get spending totals by month for a given year"""
    query = db.query(
        extract('month', ProcurementRequest.created_at).label('month'),
        func.sum(ProcurementRequest.total_amount).label('total'),
        func.count(ProcurementRequest.id).label('count')
    ).filter(
        extract('year', ProcurementRequest.created_at) == year,
        ProcurementRequest.status.in_(['approved', 'ordered', 'received', 'complete'])
    )
    
    if department:
        query = query.filter(ProcurementRequest.department == department)
    
    results = query.group_by(
        extract('month', ProcurementRequest.created_at)
    ).order_by('month').all()
    
    # Build response with all months
    months = {r.month: r for r in results}
    response = []
    
    for month in range(1, 13):
        if month in months:
            r = months[month]
            total = r.total or Decimal(0)
            count = r.count
            avg = total / count if count > 0 else Decimal(0)
        else:
            total = Decimal(0)
            count = 0
            avg = Decimal(0)
        
        response.append(SpendingReport(
            period=f"{year}-{month:02d}",
            department=department,
            total_amount=total,
            request_count=count,
            avg_amount=avg
        ))
    
    return response


@router.get("/spending/by-department", response_model=List[SpendingReport])
async def spending_by_department(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get spending totals by department"""
    query = db.query(
        ProcurementRequest.department,
        func.sum(ProcurementRequest.total_amount).label('total'),
        func.count(ProcurementRequest.id).label('count')
    ).filter(
        ProcurementRequest.status.in_(['approved', 'ordered', 'received', 'complete'])
    )
    
    if start_date:
        query = query.filter(ProcurementRequest.created_at >= start_date)
    if end_date:
        query = query.filter(ProcurementRequest.created_at <= end_date)
    
    results = query.group_by(ProcurementRequest.department).all()
    
    response = []
    for r in results:
        total = r.total or Decimal(0)
        count = r.count
        avg = total / count if count > 0 else Decimal(0)
        
        response.append(SpendingReport(
            period="all",
            department=r.department or "Unassigned",
            total_amount=total,
            request_count=count,
            avg_amount=avg
        ))
    
    return sorted(response, key=lambda x: x.total_amount, reverse=True)


@router.get("/spending/by-category", response_model=List[dict])
async def spending_by_category(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get spending totals by line item category"""
    query = db.query(
        LineItem.category,
        func.sum(LineItem.total_price).label('total'),
        func.count(LineItem.id).label('item_count')
    ).join(
        ProcurementRequest
    ).filter(
        ProcurementRequest.status.in_(['approved', 'ordered', 'received', 'complete'])
    )
    
    if start_date:
        query = query.filter(ProcurementRequest.created_at >= start_date)
    if end_date:
        query = query.filter(ProcurementRequest.created_at <= end_date)
    
    results = query.group_by(LineItem.category).all()
    
    return [
        {
            "category": r.category or "Uncategorized",
            "total_amount": float(r.total or 0),
            "item_count": r.item_count
        }
        for r in sorted(results, key=lambda x: x.total or 0, reverse=True)
    ]


# =============================================================================
# VENDOR REPORTS
# =============================================================================

@router.get("/vendors", response_model=List[VendorReport])
async def vendor_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get spending by vendor"""
    query = db.query(
        LineItem.vendor,
        func.sum(LineItem.total_price).label('total'),
        func.count(LineItem.id).label('item_count'),
        func.count(func.distinct(LineItem.request_id)).label('request_count')
    ).join(
        ProcurementRequest
    ).filter(
        ProcurementRequest.status.in_(['approved', 'ordered', 'received', 'complete']),
        LineItem.vendor.isnot(None),
        LineItem.vendor != ''
    )
    
    if start_date:
        query = query.filter(ProcurementRequest.created_at >= start_date)
    if end_date:
        query = query.filter(ProcurementRequest.created_at <= end_date)
    
    results = query.group_by(LineItem.vendor).order_by(
        func.sum(LineItem.total_price).desc()
    ).limit(limit).all()
    
    return [
        VendorReport(
            vendor=r.vendor,
            total_amount=r.total or Decimal(0),
            item_count=r.item_count,
            request_count=r.request_count
        )
        for r in results
    ]


# =============================================================================
# STATUS / PIPELINE REPORTS
# =============================================================================

@router.get("/status", response_model=List[StatusReport])
async def status_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get counts and amounts by status (current pipeline)"""
    results = db.query(
        ProcurementRequest.status,
        func.count(ProcurementRequest.id).label('count'),
        func.sum(ProcurementRequest.total_amount).label('total')
    ).group_by(ProcurementRequest.status).all()
    
    # Define order
    status_order = ['draft', 'pending', 'approved', 'rejected', 'ordered', 'received', 'complete', 'cancelled']
    status_map = {r.status: r for r in results}
    
    response = []
    for status in status_order:
        if status in status_map:
            r = status_map[status]
            response.append(StatusReport(
                status=status,
                count=r.count,
                total_amount=r.total or Decimal(0)
            ))
        else:
            response.append(StatusReport(
                status=status,
                count=0,
                total_amount=Decimal(0)
            ))
    
    return response


@router.get("/pipeline/aging")
async def pipeline_aging(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get aging report for requests in active statuses"""
    now = datetime.utcnow()
    
    # Query requests in active statuses
    requests = db.query(ProcurementRequest).filter(
        ProcurementRequest.status.in_(['pending', 'approved', 'ordered'])
    ).all()
    
    # Bucket by age
    buckets = {
        "0-7 days": [],
        "8-14 days": [],
        "15-30 days": [],
        "30+ days": []
    }
    
    for req in requests:
        age = (now - req.created_at).days
        
        if age <= 7:
            bucket = "0-7 days"
        elif age <= 14:
            bucket = "8-14 days"
        elif age <= 30:
            bucket = "15-30 days"
        else:
            bucket = "30+ days"
        
        buckets[bucket].append({
            "id": req.id,
            "title": req.title,
            "status": req.status,
            "age_days": age,
            "total_amount": float(req.total_amount or 0)
        })
    
    return {
        bucket: {
            "count": len(items),
            "total_amount": sum(i["total_amount"] for i in items),
            "requests": items
        }
        for bucket, items in buckets.items()
    }


# =============================================================================
# EXPORT
# =============================================================================

@router.get("/export/requests")
async def export_requests(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    format: str = Query("csv", regex="^(csv|xlsx)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export requests to CSV or Excel"""
    query = db.query(ProcurementRequest).join(User)
    
    if start_date:
        query = query.filter(ProcurementRequest.created_at >= start_date)
    if end_date:
        query = query.filter(ProcurementRequest.created_at <= end_date)
    if status:
        query = query.filter(ProcurementRequest.status == status)
    
    requests = query.order_by(ProcurementRequest.created_at.desc()).all()
    
    # Build data rows
    headers = [
        "ID", "Title", "Requester", "Department", "Status", "Priority",
        "Total Amount", "Budget Code", "Created", "Needed By", "PO Number"
    ]
    
    rows = []
    for req in requests:
        rows.append([
            req.id,
            req.title,
            req.requester.name if req.requester else "",
            req.department or "",
            req.status,
            req.priority,
            float(req.total_amount or 0),
            req.budget_code or "",
            req.created_at.strftime("%Y-%m-%d") if req.created_at else "",
            req.needed_by.strftime("%Y-%m-%d") if req.needed_by else "",
            req.po_number or ""
        ])
    
    if format == "csv":
        # Generate CSV
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=procurement_export.csv"}
        )
    
    else:
        # Generate Excel
        from openpyxl import Workbook
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Procurement Requests"
        
        # Headers
        ws.append(headers)
        
        # Data
        for row in rows:
            ws.append(row)
        
        # Format header row
        for cell in ws[1]:
            cell.font = cell.font.copy(bold=True)
        
        # Auto-width columns
        for column in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in column)
            ws.column_dimensions[column[0].column_letter].width = min(max_length + 2, 50)
        
        # Save to bytes
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=procurement_export.xlsx"}
        )
