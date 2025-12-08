import os
import logging
import json
import base64
import hmac
from functools import wraps
import traceback
from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import select, func
from flask_wtf.csrf import CSRFProtect, generate_csrf
from datetime import datetime, timedelta
from lead_generation_app.database.database import get_session, init_db
from lead_generation_app.database.models import BusinessClient, Payment, DeliveredLead, QualifiedLead, OptOut, Bounce, LeadSource, LoginUser
from lead_generation_app.payments import update_subscription
from lead_generation_app.payments import is_client_active
from lead_generation_app.analytics import (
    lead_to_qualified_rate_by_platform,
    qualified_to_delivered_rate_by_client_platform,
    delivered_opened_bounced_rates_by_client_platform,
)
from lead_generation_app.config.pricing import BASE_PLANS

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or os.urandom(24).hex()
is_production = os.getenv('RENDER') is not None
app.config.update(
    PERMANENT_SESSION_LIFETIME=86400,
    REMEMBER_COOKIE_DURATION=timedelta(days=30),
    PREFERRED_URL_SCHEME='https',
    APPLICATION_ROOT='/',
    SESSION_COOKIE_SECURE=is_production,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    REMEMBER_COOKIE_SECURE=is_production,
    REMEMBER_COOKIE_HTTPONLY=True
)
logging.debug(f"Production mode: {is_production}, Secure cookies: {is_production}")
csrf = CSRFProtect(app)

@app.context_processor
def inject_csrf_token():
    from flask_wtf.csrf import generate_csrf as _gen
    return dict(csrf_token=lambda: _gen())

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return LoginUser.get(user_id)

# ============ API KEY AUTHENTICATION ============
API_KEYS = {
    os.environ.get('API_KEY'): True
}

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({"error": "Missing API key"}), 401
        if api_key not in API_KEYS:
            return jsonify({"error": "Invalid API key"}), 401
        return f(*args, **kwargs)
    return decorated_function
# ============ END API KEY AUTHENTICATION ============

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

@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = (request.form.get('username', '') or '').strip()
        password = (request.form.get('password', '') or '').strip()
        remember = (request.form.get('remember') == 'on')
        user = LoginUser.get(1)
        if user and user.username == username and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        return render_template('login.html', error='Invalid username or password')
    try:
        return render_template('login.html')
    except Exception as e:
        print(f"LOGIN PAGE ERROR: {e}")
        print(traceback.format_exc())
        raise

@app.route('/admin/')
@login_required
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
@login_required
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
@login_required
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
@login_required
def update_plan(client_id):
    plan = request.form.get('plan')
    update_subscription(client_id, plan_name=plan, number_of_users=None, payment_status='paid')
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/admin/optout/add', methods=['POST'])
@login_required
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
@login_required
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
    if request.path == '/admin/health':
        return
    if request.path == '/admin/login':
        return
    if request.path.startswith('/admin/'):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))

@app.route('/admin/clients/<int:client_id>/soft-delete', methods=['POST'])
@login_required
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

# ============ API ENDPOINT FOR SOFT-DELETE ============
@app.route('/api/admin/clients/<int:client_id>/soft-delete', methods=['POST'])
@require_api_key
@csrf.exempt
def api_soft_delete_client(client_id):
    """API version of soft delete - returns JSON, no CSRF"""
    s = get_session()
    try:
        c = s.execute(select(BusinessClient).where(BusinessClient.id == client_id)).scalars().first()
        if not c:
            return jsonify({
                "status": "error",
                "message": f"Client {client_id} not found"
            }), 404
            
        c.is_deleted = True
        try:
            from datetime import datetime
            c.deleted_at = datetime.utcnow()
        except Exception:
            pass
        s.commit()
        
        return jsonify({
            "status": "success",
            "message": f"Client {client_id} soft deleted",
            "client_id": client_id,
            "timestamp": datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        s.rollback()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    finally:
        s.close()
# ============ END API ENDPOINT ============

@app.route('/admin/clients/deleted')
@login_required
def deleted_clients():
    s = get_session()
    try:
        rows = s.execute(select(BusinessClient).where(BusinessClient.is_deleted.is_(True))).scalars().all()
        return render_template('clients.html', clients=rows, show_deleted=True)
    finally:
        s.close()

@app.route('/admin/clients/<int:client_id>/restore', methods=['POST'])
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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

@app.route('/admin/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    main()
