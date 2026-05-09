from flask import Flask, render_template, request, redirect, session, flash, send_from_directory, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import os, re, pymysql, qrcode

load_dotenv()
app = Flask(
    __name__,
    template_folder='app/templates',
    static_folder='app/static'
)
app.secret_key = os.getenv('SECRET_KEY','secret')

TEXT = {
 'en': {'brand':'MemoryVerse','login':'Login','register':'Register','dashboard':'Dashboard','logout':'Logout','start':'Start Building','home_title':'Create Emotional Surprise Websites','home_subtitle':'Build memories with stories, games, wishes, reactions and QR share.','create':'Create Surprise','save':'Save','publish':'Publish','edit':'Edit','share':'Share','memories':'Memories'},
 'hi': {'brand':'मेमोरीवर्स','login':'लॉगिन','register':'रजिस्टर','dashboard':'डैशबोर्ड','logout':'लॉगआउट','start':'बनाना शुरू करें','home_title':'अपनों के लिए इमोशनल सरप्राइज वेबसाइट बनाएं','home_subtitle':'यादों, गेम्स, शुभकामनाओं, रिएक्शन और QR के साथ सरप्राइज बनाएं।','create':'सरप्राइज बनाएं','save':'सेव','publish':'पब्लिश','edit':'एडिट','share':'शेयर','memories':'यादें'}
}

def t(k): return TEXT.get(session.get('lang','en'), TEXT['en']).get(k,k)
app.jinja_env.globals.update(t=t)

def conn():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        cursorclass=pymysql.cursors.DictCursor
    )

def one(sql,args=()):
    c=conn();
    try:
        with c.cursor() as cur: cur.execute(sql,args); return cur.fetchone()
    finally: c.close()

def allq(sql,args=()):
    c=conn();
    try:
        with c.cursor() as cur: cur.execute(sql,args); return cur.fetchall()
    finally: c.close()

def execq(sql,args=()):
    c=conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql,args)
            c.commit()
            return cur.lastrowid
    finally:
        c.close()

def slugify(s): return re.sub(r'[^a-zA-Z0-9]+','-',s.lower()).strip('-') or 'surprise'

@app.route('/uploads/<path:name>')
def uploads(name): return send_from_directory('app/static/uploads', name)

@app.route('/')
def home(): return render_template('home.html')

@app.route('/lang/<lang>')
def lang(lang): session['lang']=lang; return redirect(request.referrer or '/')
@app.route('/mode/<mode>')
def mode(mode): session['mode']=mode; return redirect(request.referrer or '/')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email'].lower()
        password = request.form['password']

        hashed = generate_password_hash(password)

        try:
            with conn() as c:
                with c.cursor() as cur:
                    cur.execute(
                        "INSERT INTO users(name,email,password_hash) VALUES(%s,%s,%s)",
                        (name, email, hashed)
                    )
                c.commit()

            flash('Registered. Login now.')
            return redirect(url_for('login'))

        except Exception as e:
            return str(e)

    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=one('SELECT * FROM users WHERE email=%s',(request.form['email'].lower(),))

        if not u or not check_password_hash(u['password_hash'], request.form['password']):
            flash('Invalid email or password')
            return redirect('/login')

        session.update(
    user_id=u['id'],
    name=u['name'],
    lang=u['language'],
    mode=u['appearance']
)

        return redirect('/dashboard')

    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'): return redirect('/login')
    events=allq('SELECT * FROM events WHERE user_id=%s ORDER BY id DESC',(session['user_id'],))
    return render_template('dashboard.html', events=events)

@app.route('/create', methods=['GET','POST'])
def create():
    if not session.get('user_id'): return redirect('/login')
    if request.method=='POST':
        slug=slugify(request.form['title'])
        if one('SELECT id FROM events WHERE slug=%s',(slug,)): slug += '-' + str(session['user_id'])
        eid=execq('INSERT INTO events(user_id,title,receiver_name,event_type,subtitle,final_message,language,appearance,slug) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)', (session['user_id'],request.form['title'],request.form['receiver_name'],request.form['event_type'],request.form.get('subtitle'),request.form.get('final_message'),request.form.get('language'),request.form.get('appearance'),slug))
        return redirect(f'/memories/{eid}')
    return render_template('create.html')

@app.route('/edit/<int:eid>', methods=['GET','POST'])
def edit(eid):
    if not session.get('user_id'): return redirect('/login')
    e=one('SELECT * FROM events WHERE id=%s AND user_id=%s',(eid,session['user_id']))
    if request.method=='POST':
        execq('UPDATE events SET title=%s,receiver_name=%s,event_type=%s,subtitle=%s,final_message=%s,language=%s,appearance=%s WHERE id=%s', (request.form['title'],request.form['receiver_name'],request.form['event_type'],request.form.get('subtitle'),request.form.get('final_message'),request.form.get('language'),request.form.get('appearance'),eid))
        return redirect('/dashboard')
    return render_template('create.html', event=e)

@app.route('/memories/<int:eid>', methods=['GET','POST'])
def memories(eid):
    if not session.get('user_id'): return redirect('/login')
    e=one('SELECT * FROM events WHERE id=%s AND user_id=%s',(eid,session['user_id']))
    if request.method=='POST':
        url=typ=None; f=request.files.get('media')
        if f and f.filename:
            ext=f.filename.rsplit('.',1)[-1].lower(); typ='image' if ext in ['png','jpg','jpeg','webp','gif'] else 'audio' if ext in ['mp3','wav','ogg'] else 'video'
            name=f'{eid}_{secure_filename(f.filename)}'; f.save(os.path.join('app/static/uploads',name)); url='/uploads/'+name
        execq('INSERT INTO memories(event_id,title,description,emotion_tag,media_url,media_type) VALUES(%s,%s,%s,%s,%s,%s)', (eid,request.form['title'],request.form['description'],request.form.get('emotion_tag'),url,typ))
        return redirect(f'/memories/{eid}')
    mem=allq('SELECT * FROM memories WHERE event_id=%s',(eid,))
    return render_template('memories.html', event=e, memories=mem)

@app.route('/publish/<int:eid>')
def publish(eid):
    if not session.get('user_id'):
        return redirect('/login')

    e = one(
        'SELECT * FROM events WHERE id=%s AND user_id=%s',
        (eid, session['user_id'])
    )

    if not e:
        return "Event not found"

    share = os.getenv(
        'APP_URL',
        'http://127.0.0.1:5000'
    ) + '/s/' + e['slug']

    qr = 'qr_' + e['slug'] + '.png'

    qrcode.make(share).save(
        os.path.join('app/static/uploads', qr)
    )

    execq(
        "UPDATE events SET status='published', qr_url=%s WHERE id=%s",
        ('/uploads/' + qr, eid)
    )

    return redirect(f'/share/{eid}')

@app.route('/share/<int:eid>')
def share(eid):
    if not session.get('user_id'): return redirect('/login')
    e=one('SELECT * FROM events WHERE id=%s AND user_id=%s',(eid,session['user_id']))
    share_url=os.getenv('APP_URL','http://127.0.0.1:5000')+'/s/'+e['slug']
    return render_template('share.html', event=e, share_url=share_url)

@app.route('/s/<slug>')
def public(slug):
    e=one('SELECT * FROM events WHERE slug=%s',(slug,))
    if not e or e['status']!='published': return render_template('not_available.html')
    mem=allq('SELECT * FROM memories WHERE event_id=%s',(e['id'],)); wishes=allq('SELECT * FROM wishes WHERE event_id=%s',(e['id'],))
    return render_template('experience.html', event=e, memories=mem, wishes=wishes)

@app.route('/s/<slug>/wish', methods=['POST'])
def wish(slug):
    e=one('SELECT * FROM events WHERE slug=%s',(slug,))
    if e: execq('INSERT INTO wishes(event_id,name,message) VALUES(%s,%s,%s)',(e['id'],request.form['name'],request.form['message']))
    return redirect('/s/'+slug)

@app.route('/s/<slug>/react/<reaction>')
def react(slug,reaction):
    e=one('SELECT * FROM events WHERE slug=%s',(slug,))
    if e: execq('INSERT INTO reactions(event_id,reaction) VALUES(%s,%s)',(e['id'],reaction))
    return {'ok':True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )
