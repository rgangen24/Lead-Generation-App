import os
import logging
import json
import base64
import hmac
from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
from sqlalchemy import select, func
from datetime import datetime, timedelta
from lead_generation_app.database.database import get_session, init_db
from lead_generation_app.database.models import BusinessClient, Payment, DeliveredLead, QualifiedLead, OptOut, Bounce, LeadSource
from lead_generation_app.payments import update_subscription
from lead_generation_app.payments import is_client_active
from lead_generation_app.analytics import (
    lead_to_qualified_rate_by_platform,
    qualified_to_delivered_rate_by_client_platform,
    delivered_opened_bounced_rates_by_client_platform,
)
from lead_generation_app.config.pricing import BASE_PLANS

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

def _init():
    with app.app_context():
        init_db()

def _month_window(now):
    start = datetime(now.year, now.month, 1)
    end = start + timedelta(days=31)
    return start, end

@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/admin/')
def dashboard():
    s = get_session()
    try:
        now = datetime.utcnow()
        start, end = _month_window(now)
        clients = s.execute(select(BusinessClient)).scalars().all()
        rows = []
        for c in clients:
            delivered = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == c.id).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
            opens = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == c.id).where(DeliveredLead.opened_status.is_(True)).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
            bounces = s.execute(select(func.count(Bounce.id))).scalar_one()
            rows.append({'id': c.id, 'name': c.business_name, 'plan': c.subscription_plan, 'cap_used': int(delivered), 'opens': int(opens), 'bounces': int(bounces)})
        return render_template('index.html', clients=rows)
    finally:
        s.close()

@app.route('/admin/clients')
def clients():
    s = get_session()
    try:
        now = datetime.utcnow()
        start, end = _month_window(now)
        rows = s.execute(select(BusinessClient).where(BusinessClient.is_deleted.is_(False))).scalars().all()
        q = (request.args.get('q') or '').strip().lower()
        plan = (request.args.get('plan') or '').strip().lower()
        data = []
        for c in rows:
            if q and q not in (c.business_name or '').lower():
                continue
            if plan and (c.subscription_plan or '').lower() != plan:
                continue
            delivered = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == c.id).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
            data.append({'id': c.id, 'name': c.business_name, 'plan': c.subscription_plan, 'cap_used': int(delivered), 'next_billing_date': (c.next_billing_date.isoformat() if c.next_billing_date else None)})
        if request.headers.get('HX-Request'):
            return render_template('clients_body.html', clients=data)
        return render_template('clients.html', clients=data, q=q, plan=plan)
    finally:
        s.close()

@app.route('/admin/clients/<int:client_id>')
def client_detail(client_id):
    s = get_session()
    try:
        now = datetime.utcnow()
        start, end = _month_window(now)
        c = s.execute(select(BusinessClient).where(BusinessClient.id == client_id)).scalars().first()
        if not c:
            return redirect(url_for('clients'))
        delivered = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == client_id).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
        opens = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == client_id).where(DeliveredLead.opened_status.is_(True)).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
        bounces = s.execute(select(func.count(Bounce.id))).scalar_one()
        optouts_email = s.execute(select(func.count(OptOut.id)).where(OptOut.method == 'email')).scalar_one()
        optouts_wa = s.execute(select(func.count(OptOut.id)).where(OptOut.method == 'whatsapp')).scalar_one()
        return render_template('client_detail.html', client=c, cap_used=int(delivered), opens=int(opens), bounces=int(bounces), optouts_email=int(optouts_email), optouts_wa=int(optouts_wa))
    finally:
        s.close()

@app.route('/admin/clients/<int:client_id>/update_plan', methods=['POST'])
def update_plan(client_id):
    plan = request.form.get('plan')
    update_subscription(client_id, plan_name=plan, number_of_users=None, payment_status='paid')
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/admin/optout/add', methods=['POST'])
def add_optout():
    method = request.form.get('method')
    value = request.form.get('value')
    s = get_session()
    try:
        row = OptOut(method=method, value=value, created_at=datetime.utcnow())
        s.add(row)
        s.commit()
        return redirect(url_for('clients'))
    finally:
        s.close()

@app.route('/admin/analytics')
def analytics():
    s = get_session()
    try:
        clients = s.execute(select(BusinessClient)).scalars().all()
        platforms = [r[0] for r in s.execute(select(LeadSource.platform_type).distinct()).all()]
    finally:
        s.close()
    client_id = request.args.get('client_id')
    platform = (request.args.get('platform') or '').strip().lower()
    ltq = lead_to_qualified_rate_by_platform()
    qtd = qualified_to_delivered_rate_by_client_platform()
    dob = delivered_opened_bounced_rates_by_client_platform()
    client_id_int = int(client_id) if client_id and client_id.isdigit() else None
    data = {
        'ltq': ltq,
        'qtd': qtd.get(client_id_int, {}) if client_id_int else qtd,
        'dob': dob.get(client_id_int, {}) if client_id_int else dob,
        'client_id': client_id_int,
        'platform': platform,
    }
    if platform:
        # Filter platform-specific slices
        data['ltq'] = {platform: ltq.get(platform, {'raw': 0, 'qualified': 0, 'rate': 0.0})}
        def _filter_pf(m):
            if client_id_int:
                return {platform: m.get(platform, {})}
            else:
                return {k: {platform: v.get(platform, {})} for k, v in m.items()}
        data['qtd'] = _filter_pf(data['qtd'])
        def _filter_dob(m):
            if client_id_int:
                return {platform: m.get(platform, {})}
            else:
                return {k: {platform: v.get(platform, {})} for k, v in m.items()}
        data['dob'] = _filter_dob(data['dob'])
    ctx = {
        'clients': clients,
        'platforms': platforms,
        'metrics': data,
    }
    if request.headers.get('HX-Request'):
        return render_template('analytics_body.html', **ctx)
    return render_template('analytics.html', **ctx)

@app.route('/admin/api/clients', methods=['GET'])
def api_clients_list():
    s = get_session()
    try:
        now = datetime.utcnow()
        start, end = _month_window(now)
        rows = s.execute(select(BusinessClient).where(BusinessClient.is_deleted.is_(False))).scalars().all()
        out = []
        for c in rows:
            delivered = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == c.id).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
            opens = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == c.id).where(DeliveredLead.opened_status.is_(True)).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
            plan = BASE_PLANS.get(c.subscription_plan) if c.subscription_plan else None
            out.append({
                'id': c.id,
                'name': c.business_name,
                'industry': c.industry,
                'email': c.email,
                'phone': c.phone,
                'whatsapp': c.whatsapp,
                'subscription_plan': c.subscription_plan,
                'plan_cap': (int(plan.get('lead_cap')) if plan else None),
                'plan_discount': (float(plan.get('discount')) if plan else None),
                'number_of_users': c.number_of_users,
                'next_billing_date': (c.next_billing_date.isoformat() if c.next_billing_date else None),
                'active': bool(is_client_active(c.id)),
                'delivered_this_month': int(delivered),
                'opens_this_month': int(opens),
            })
        body = json.dumps(out).encode('utf-8')
        return Response(body, 200, {'Content-Type': 'application/json'})
    finally:
        s.close()

@app.route('/admin/api/clients/<int:client_id>', methods=['GET'])
def api_client_detail(client_id):
    s = get_session()
    try:
        now = datetime.utcnow()
        start, end = _month_window(now)
        c = s.execute(select(BusinessClient).where(BusinessClient.id == client_id)).scalars().first()
        if not c:
            return Response(json.dumps({'error': 'not_found'}).encode('utf-8'), 404, {'Content-Type': 'application/json'})
        delivered = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == client_id).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
        opens = s.execute(select(func.count(DeliveredLead.id)).where(DeliveredLead.business_client_id == client_id).where(DeliveredLead.opened_status.is_(True)).where(DeliveredLead.delivered_at >= start).where(DeliveredLead.delivered_at < end)).scalar_one()
        bounces = s.execute(select(func.count(Bounce.id))).scalar_one()
        optouts_email = s.execute(select(func.count(OptOut.id)).where(OptOut.method == 'email')).scalar_one()
        optouts_wa = s.execute(select(func.count(OptOut.id)).where(OptOut.method == 'whatsapp')).scalar_one()
        plan = BASE_PLANS.get(c.subscription_plan) if c.subscription_plan else None
        body = json.dumps({
            'id': c.id,
            'name': c.business_name,
            'industry': c.industry,
            'email': c.email,
            'phone': c.phone,
            'whatsapp': c.whatsapp,
            'subscription_plan': c.subscription_plan,
            'plan_cap': (int(plan.get('lead_cap')) if plan else None),
            'plan_discount': (float(plan.get('discount')) if plan else None),
            'number_of_users': c.number_of_users,
            'next_billing_date': (c.next_billing_date.isoformat() if c.next_billing_date else None),
            'active': bool(is_client_active(c.id)),
            'delivered_this_month': int(delivered),
            'opens_this_month': int(opens),
            'bounces_total': int(bounces),
            'optouts_email_total': int(optouts_email),
            'optouts_whatsapp_total': int(optouts_wa),
        }).encode('utf-8')
        return Response(body, 200, {'Content-Type': 'application/json'})
    finally:
        s.close()

@app.route('/admin/api/leads', methods=['GET'])
def api_leads_list():
    s = get_session()
    try:
        industry = (request.args.get('industry') or '').strip()
        category = (request.args.get('category') or '').strip().lower()
        min_score = request.args.get('min_score')
        limit = request.args.get('limit')
        offset = request.args.get('offset')
        q = select(QualifiedLead)
        if industry:
            q = q.where(QualifiedLead.industry == industry)
        if category:
            q = q.where(QualifiedLead.score_category == category)
        if min_score and str(min_score).isdigit():
            q = q.where(QualifiedLead.qualification_score >= int(min_score))
        if offset and str(offset).isdigit():
            q = q.offset(int(offset))
        if limit and str(limit).isdigit():
            q = q.limit(int(limit))
        rows = s.execute(q).scalars().all()
        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'raw_lead_id': r.raw_lead_id,
                'name': r.name,
                'company_name': r.company_name,
                'email': r.email,
                'phone': r.phone,
                'industry': r.industry,
                'score_category': r.score_category,
                'qualification_score': r.qualification_score,
                'verified_status': bool(r.verified_status),
                'summary': r.summary or '',
            })
        body = json.dumps(out).encode('utf-8')
        return Response(body, 200, {'Content-Type': 'application/json'})
    finally:
        s.close()

@app.route('/admin/api/clients', methods=['POST'])
def api_client_create():
    s = get_session()
    try:
        payload = None
        try:
            payload = request.get_json(silent=True)
        except Exception:
            payload = None
        if not isinstance(payload, dict):
            return Response(json.dumps({'error': 'invalid_json'}).encode('utf-8'), 400, {'Content-Type': 'application/json'})
        name = (payload.get('name') or payload.get('business_name') or '').strip()
        if not name:
            return Response(json.dumps({'error': 'name_required'}).encode('utf-8'), 400, {'Content-Type': 'application/json'})
        industry = (payload.get('industry') or '').strip()
        email = (payload.get('email') or '').strip()
        phone = (payload.get('phone') or '').strip()
        whatsapp = (payload.get('whatsapp') or '').strip()
        plan_name = (payload.get('subscription_plan') or '').strip() or None
        users = payload.get('number_of_users')
        bc = BusinessClient(business_name=name, industry=industry or None, email=email or None, phone=phone or None, whatsapp=whatsapp or None, subscription_plan=plan_name or None, number_of_users=(int(users) if users is not None else None), next_billing_date=None)
        s.add(bc)
        s.commit()
        payment_status = (payload.get('payment_status') or '').strip().lower()
        if plan_name and payment_status in ('paid', 'success'):
            update_subscription(bc.id, plan_name=plan_name, number_of_users=(int(users) if users is not None else None), payment_status=payment_status)
        plan = BASE_PLANS.get(plan_name) if plan_name else None
        body = json.dumps({
            'id': bc.id,
            'name': bc.business_name,
            'industry': bc.industry,
            'email': bc.email,
            'phone': bc.phone,
            'whatsapp': bc.whatsapp,
            'subscription_plan': bc.subscription_plan,
            'plan_cap': (int(plan.get('lead_cap')) if plan else None),
            'plan_discount': (float(plan.get('discount')) if plan else None),
            'number_of_users': bc.number_of_users,
            'next_billing_date': (bc.next_billing_date.isoformat() if bc.next_billing_date else None),
            'active': bool(is_client_active(bc.id)),
        }).encode('utf-8')
        return Response(body, 201, {'Content-Type': 'application/json'})
    finally:
        s.close()

@app.before_request
def _protect_admin():
    if request.path.startswith('/admin'):
        auth = request.headers.get('Authorization', '')
        ok = False
        if auth.startswith('Basic '):
            try:
                raw = base64.b64decode(auth.split(' ', 1)[1]).decode('utf-8')
                if ':' in raw:
                    u, p = raw.split(':', 1)
                    ok = hmac.compare_digest(u, os.getenv('ADMIN_USER', 'admin')) and hmac.compare_digest(p, os.getenv('ADMIN_PASS', 'admin'))
            except Exception:
                ok = False
        if not ok:
            return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Admin"'})

@app.route('/admin/clients/<int:client_id>/soft-delete', methods=['POST'])
def soft_delete_client(client_id):
    s = get_session()
    try:
        c = s.execute(select(BusinessClient).where(BusinessClient.id == client_id)).scalars().first()
        if c:
            c.is_deleted = True
            try:
                from datetime import datetime
                c.deleted_at = datetime.utcnow()
            except Exception:
                pass
            s.commit()
        return redirect(url_for('clients'))
    finally:
        s.close()

@app.route('/admin/clients/deleted')
def deleted_clients():
    s = get_session()
    try:
        rows = s.execute(select(BusinessClient).where(BusinessClient.is_deleted.is_(True))).scalars().all()
        return render_template('clients.html', clients=rows, show_deleted=True)
    finally:
        s.close()

@app.route('/admin/clients/<int:client_id>/restore', methods=['POST'])
def restore_client(client_id):
    s = get_session()
    try:
        c = s.execute(select(BusinessClient).where(BusinessClient.id == client_id)).scalars().first()
        if c:
            c.is_deleted = False
            c.deleted_at = None
            s.commit()
        return redirect(url_for('deleted_clients'))
    finally:
        s.close()

@app.route('/admin/clients/<int:client_id>/permanent-delete', methods=['POST'])
def permanent_delete_client(client_id):
    s = get_session()
    try:
        c = s.execute(select(BusinessClient).where(BusinessClient.id == client_id)).scalars().first()
        if c:
            s.delete(c)
            s.commit()
        return redirect(url_for('deleted_clients'))
    finally:
        s.close()

@app.route('/admin/clients/bulk-soft-delete', methods=['POST'])
def bulk_soft_delete():
    ids = request.form.getlist('client_ids')
    s = get_session()
    try:
        if ids:
            for i in ids:
                try:
                    cid = int(i)
                except Exception:
                    continue
                c = s.execute(select(BusinessClient).where(BusinessClient.id == cid)).scalars().first()
                if c:
                    c.is_deleted = True
                    c.deleted_at = datetime.utcnow()
            s.commit()
        return redirect(url_for('clients'))
    finally:
        s.close()

@app.route('/admin/clients/bulk-restore', methods=['POST'])
def bulk_restore():
    ids = request.form.getlist('client_ids')
    s = get_session()
    try:
        if ids:
            for i in ids:
                try:
                    cid = int(i)
                except Exception:
                    continue
                c = s.execute(select(BusinessClient).where(BusinessClient.id == cid)).scalars().first()
                if c:
                    c.is_deleted = False
                    c.deleted_at = None
            s.commit()
        return redirect(url_for('deleted_clients'))
    finally:
        s.close()

@app.route('/admin/clients/bulk-permanent-delete', methods=['POST'])
def bulk_permanent_delete():
    ids = request.form.getlist('client_ids')
    s = get_session()
    try:
        if ids:
            for i in ids:
                try:
                    cid = int(i)
                except Exception:
                    continue
                c = s.execute(select(BusinessClient).where(BusinessClient.id == cid)).scalars().first()
                if c:
                    s.delete(c)
            s.commit()
        return redirect(url_for('deleted_clients'))
    finally:
        s.close()

@app.route('/admin/health')
def admin_health():
    ts = datetime.utcnow().isoformat()
    s = get_session()
    try:
        s.execute(select(func.count(BusinessClient.id))).scalar_one()
        return jsonify(status='healthy', timestamp=ts), 200
    except Exception:
        return jsonify(status='unhealthy', timestamp=ts), 503
def main():
    logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
    logging.info('{"event":"admin_web_start"}')
    raw = os.getenv('PORT') or os.getenv('ADMIN_PORT') or '8081'
    try:
        port = int(raw)
    except Exception:
        port = 8081
    _init()
    logging.info('{"event":"admin_web_bind","port":%d}' % port)
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    main()


