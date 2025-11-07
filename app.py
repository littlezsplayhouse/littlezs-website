from flask import Flask, request, redirect, url_for, render_template_string, flash, session
import csv, os, json, time
from datetime import datetime, timezone
import base64
import glob, mimetypes
import socket
from urllib import request as urlreq
from urllib.parse import urlencode

# -------- Settings --------
HOST = "0.0.0.0"
PREFERRED_PORT_START = 5077
PREFERRED_PORT_END = 5090
VERSION = "v1.1"

# -------- Secure configuration --------
# Real values will be stored later as environment variables (not in code)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "testpassword")

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
GOOGLE_PLACE_ID = os.getenv("GOOGLE_PLACE_ID", "").strip()
GOOGLE_MAPS_LINK = os.getenv("GOOGLE_MAPS_LINK", "").strip()
GOOGLE_CACHE_FILE = "google_rating_cache.json"
GOOGLE_CACHE_TTL_SECONDS = 4 * 60 * 60  # 4 hours  [UPDATED]

app = Flask(__name__)
app.secret_key = "littlezs-dev"   # change for deployment

# -------- Data files --------
CSV_FILE = "contact_submissions.csv"
FEEDBACK_FILE = "feedback.csv"

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["timestamp", "name", "email", "phone", "message"])

if not os.path.exists(FEEDBACK_FILE):
    with open(FEEDBACK_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            ["id","timestamp","name","relationship","rating","comment","can_publish","approved"]
        )

# -------- Logo helper --------
def logo_data_url():
    """Return data:image/...;base64,... for any logo file (png, jpg, jpeg)."""
    for name in sorted(glob.glob("logo*")):  # logo.png, logo.jpg, logo.jpeg...
        if os.path.isfile(name):
            mime = mimetypes.guess_type(name)[0] or "image/png"
            with open(name, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return f"data:{mime};base64,{b64}"
    return None

# -------- Google rating helpers (optional) --------
def _load_google_cache():
    try:
        if os.path.exists(GOOGLE_CACHE_FILE):
            with open(GOOGLE_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if time.time() - float(data.get("_ts", 0)) < GOOGLE_CACHE_TTL_SECONDS:
                return data
    except Exception:
        pass
    return None

def _save_google_cache(payload):
    try:
        payload["_ts"] = time.time()
        with open(GOOGLE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass

def fetch_google_rating():
    """
    Returns dict like: {"rating": 4.9, "count": 27, "link": "..."} or None if not available.
    Uses JSON cache for speed/reliability. Safe fallback if no API key.
    """
    # If no API key, show only link if provided.
    if not GOOGLE_PLACES_API_KEY:
        if GOOGLE_MAPS_LINK:
            return {"rating": None, "count": None, "link": GOOGLE_MAPS_LINK}
        return None

    # Try cache first
    cached = _load_google_cache()
    if cached:
        return {
            "rating": cached.get("rating"),
            "count": cached.get("count"),
            "link": cached.get("link") or GOOGLE_MAPS_LINK
        }

    # Fetch live (Place Details: rating + user_ratings_total)
    try:
        params = {
            "place_id": GOOGLE_PLACE_ID,
            "fields": "rating,user_ratings_total",
            "key": GOOGLE_PLACES_API_KEY
        }
        url = "https://maps.googleapis.com/maps/api/place/details/json?" + urlencode(params)
        with urlreq.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = data.get("result", {}) if isinstance(data, dict) else {}
        rating = result.get("rating")
        count = result.get("user_ratings_total")
        payload = {"rating": rating, "count": count, "link": GOOGLE_MAPS_LINK}
        _save_google_cache(payload)
        return payload
    except Exception:
        # On any error, fall back to link only (if any)
        if GOOGLE_MAPS_LINK:
            return {"rating": None, "count": None, "link": GOOGLE_MAPS_LINK}
        return None

# -------- Base HTML (unchanged except using google + version) --------
BASE = """
{% set brand = "Little Z’s Playhouse Daycare" %}
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
  <meta http-equiv="Pragma" content="no-cache" />
  <meta http-equiv="Expires" content="0" />
  <title>{{ title }} · {{ brand }}</title>
  <meta name="description" content="Little Z’s Playhouse Daycare in Farmingdale, NY. Licensed care for ages 6 weeks–5 years. Healthy meals, safe backyard play, and loving, family-style learning. Book a tour.">
  <style>
    :root{--teal:#7bc4d4;--pink:#f4a9c4;--ink:#263238;--bg:#f3fafc;--softgray:#8a9aa5;--green:#16c172}
    *{box-sizing:border-box}
    body{margin:0;font-family:-apple-system,system-ui,Arial;color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale}

    header{
      text-align:center;
      padding:1.2rem 0 .8rem;
      border-bottom:1px solid #e9eef1;
      background:linear-gradient(135deg, #fde4ec, #e0f7fa 70%, #ffffff);
      position: sticky;
      top: 0;
      z-index: 10000;
      -webkit-transform: translateZ(0);
    }

    .brand-logo{
      display:block;margin:0 auto .5rem;
      width:min(200px, 45vw);
      height:auto;
      border-radius:12px;
      object-fit:contain;
      background:#fff;
      padding:8px;
      box-shadow:0 4px 10px rgba(0,0,0,0.12);
    }

    .nav-centered{
      display:flex;justify-content:center;flex-wrap:wrap;gap:.5rem;margin-top:.5rem;
      position: relative;
      z-index: 10001;
      pointer-events: auto;
    }
    .nav-centered a{
      color:var(--ink);text-decoration:none;padding:.55rem .9rem;border-radius:10px;font-weight:500;
      -webkit-tap-highlight-color: transparent;
    }
    .nav-centered a.active, .nav-centered a:hover{background:#eef7fa;color:var(--teal);}

    .wrap{max-width:920px;margin:1rem auto;padding:0 1rem}

    .hero{
      background:linear-gradient(180deg,#e9f7fb,#ffffff);
      padding:1.2rem 1rem;border-radius:14px;
      box-shadow:0 6px 22px rgba(20,30,40,.05);
      position: relative;
      z-index: 1;
    }

    .tour-box{
      display:inline-block;text-decoration:none;color:var(--ink);background:#fff;border-radius:10px;
      padding:.95rem 1.25rem;margin-top:1.0rem;box-shadow:0 4px 14px rgba(0,0,0,.08);
      transition:transform .15s ease, box-shadow .15s ease;
      border:1px solid #e8eef2;
    }
    .tour-box:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(0,0,0,.10)}

    h1,h2{color:var(--teal);margin:.2rem 0 .6rem}
    .card{background:#fff;padding:1rem;border-radius:12px;box-shadow:0 6px 18px rgba(20,30,40,.06);margin:.9rem 0;transition:transform .15s ease, box-shadow .15s ease}
    .card:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(20,30,40,.10)}
    .btn{display:inline-block;background:var(--pink);color:#fff;padding:.6rem 1rem;border-radius:10px;text-decoration:none}
    .btn:hover{transform:translateY(-1px); box-shadow:0 6px 16px rgba(0,0,0,.12)}
    .grid{display:grid;gap:1rem}
    @media(min-width:700px){.grid-2{grid-template-columns:1fr 1fr}}
    .muted{opacity:.85}

    .foot{padding:1.2rem 1rem;color:var(--teal);text-align:center}
    .foot-row{display:flex;gap:.5rem;align-items:center;justify-content:center;flex-wrap:wrap}
    .foot-ver{display:inline-flex;align-items:center;gap:.45rem;color:var(--softgray);font-weight:500}
    .dot{display:inline-block;width:.65rem;height:.65rem;border-radius:50%;background:var(--green);box-shadow:0 0 10px rgba(22,193,114,.6);}

    .alert{background:#e6fff1;border:1px solid #b6f0cd;color:#225a36;padding:.6rem .8rem;border-radius:10px;margin:.6rem 0}
    label{display:block;margin:.5rem 0 .25rem}
    input,textarea,select{width:100%;padding:.7rem .8rem;border:1px solid #d7e3ea;border-radius:10px}

    table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 6px 18px rgba(20,30,40,.06)}
    th,td{padding:.7rem .8rem;border-bottom:1px solid #eef2f5;vertical-align:top}
    th{background:#f8fbfd;color:#4a6572;text-align:left}
    tr:last-child td{border-bottom:none}
    .admin-actions{display:flex;gap:.5rem;flex-wrap:wrap;margin:.6rem 0}
    .muted-small{opacity:.7;font-size:.9rem}
    .stars{font-size:1.1rem;color:#f6b800}

    .g-badge{display:inline-flex;align-items:center;gap:.5rem;background:#fff;border:1px solid #e8eef2;border-radius:999px;padding:.35rem .6rem;margin-top:.6rem;box-shadow:0 2px 8px rgba(0,0,0,.06)}
    .g-chip{display:inline-flex;align-items:center;gap:.35rem}
    .g-logo{width:18px;height:18px;display:inline-block;background:
      conic-gradient(from 45deg,#4285F4 0 25%,#34A853 0 50%,#FBBC05 0 75%,#EA4335 0 100%);
      -webkit-mask: radial-gradient(circle at 50% 50%, transparent 6px, #000 7px);
      mask: radial-gradient(circle at 50% 50%, transparent 6px, #000 7px);
      border-radius:50%;
    }
    .g-num{font-weight:700}
    .g-link{color:var(--teal);text-decoration:none}
  </style>
  {% if logo %}<link rel="icon" href="{{ logo }}" type="image/png">{% endif %}

  {% if google and google.rating %}
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "ChildCare",
    "name": "Little Z’s Playhouse Daycare",
    "address": {"@type":"PostalAddress","streetAddress":"41 Lincoln St","addressLocality":"Farmingdale","addressRegion":"NY","postalCode":"11735","addressCountry":"US"},
    "aggregateRating": {"@type":"AggregateRating","ratingValue":"{{ '%.1f'|format(google.rating) }}","reviewCount":"{{ google.count or 0 }}"}
  }
  </script>
  {% endif %}
</head>
<body>
  <header>
    {% if logo %}
      <img class="brand-logo" src="{{ logo }}" alt="Little Z’s Playhouse logo">
    {% endif %}
    <div style="font-size:1.6rem;font-weight:700;color:var(--ink);">Little Z’s Playhouse</div>
    <div style="font-size:1rem;color:var(--teal);font-weight:500;">Farmingdale, NY</div>

    <nav class="nav-centered" role="navigation" aria-label="Primary">
      <a data-nav href="{{ url_for('home') }}" class="{% if page=='home' %}active{% endif %}">Home</a>
      <a data-nav href="{{ url_for('about') }}" class="{% if page=='about' %}active{% endif %}">About</a>
      <a data-nav href="{{ url_for('programs') }}" class="{% if page=='programs' %}active{% endif %}">Programs</a>
      <a data-nav href="{{ url_for('contact') }}" class="{% if page=='contact' %}active{% endif %}">Contact</a>
      <a data-nav href="{{ url_for('testimonials') }}" class="{% if page=='testimonials' %}active{% endif %}">Testimonials</a>
      <a data-nav href="{{ url_for('reviews') }}" class="{% if page=='reviews' %}active{% endif %}">Reviews</a>
      <a data-nav href="{{ url_for('feedback') }}" class="{% if page=='feedback' %}active{% endif %}">Leave Feedback</a>
      <a data-nav href="{{ url_for('admin_login') }}" class="{% if page=='admin' %}active{% endif %}">Admin</a>
    </nav>

    {% if google %}
      <div class="g-badge" aria-label="Google reviews">
        <span class="g-logo" aria-hidden="true"></span>
        {% if google.rating %}
          <span class="g-chip"><span class="g-num">{{ '%.1f'|format(google.rating) }}</span>★</span>
          <span class="muted">({{ google.count or 0 }})</span>
        {% endif %}
        {% if google.link %}
          <a class="g-link" href="{{ google.link }}" target="_blank" rel="noopener">See reviews</a>
        {% endif %}
      </div>
    {% endif %}
  </header>

  <main class="wrap">
    {% with msgs = get_flashed_messages() %}
      {% if msgs %}{% for m in msgs %}<div class="alert">{{ m }}</div>{% endfor %}{% endif %}
    {% endwith %}
    {{ body|safe }}
  </main>

   <footer class="foot">
    <div class="foot-row">
      <span>41 Lincoln St, Farmingdale, NY • Mon–Fri 7:30 a.m.–5:00 p.m. • Nap 1–3 p.m.</span>
      • <a href="tel:+15169127375" style="color:inherit;">516-912-7375</a>
      • <a href="mailto:littlezsplayhouse@gmail.com" style="color:inherit;">littlezsplayhouse@gmail.com</a>
      • <span class="foot-ver"><span class="dot" aria-label="Server alive"></span> {{ version }}</span>
    </div>
  </footer>

  <!-- iOS tap helper: make header links AND buttons always navigate -->
  <script>
  (function () {
    function handleTap(e) {
      var a = e.target.closest && e.target.closest('a[data-nav], a[data-go], a.btn');
      if (!a || !a.href) return;

      var href = a.getAttribute('href') || '';
      if (!href || href === '#') return;

      // Let iPhone handle phone/email links natively
      if (href.indexOf('tel:') === 0 || href.indexOf('mailto:') === 0) {
        return; // no preventDefault for tel/mailto
      }

      // For normal links, do a safe navigate
      e.preventDefault();
      if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
      }
      setTimeout(function () { window.location.href = href; }, 40);
    }

    document.addEventListener('touchend', handleTap, { passive: false });
    document.addEventListener('click',    handleTap, { passive: false });
  })();
  </script>
</body>
</html>
"""
def render(page, title, body):
    # pull Google rating each render (fast via cache; safe fallback if no key)
    google = fetch_google_rating()
    return render_template_string(
        BASE,
        page=page, title=title, body=body,
        logo=logo_data_url(),
        google=google,
        version=VERSION
    )

# -------- No-cache for every response (prevents freeze from stale caches) --------
@app.after_request
def add_no_cache_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# -------- Public Pages --------
@app.route("/")
def home():
    body = """
    <section class="hero" style="text-align:center;padding:2rem 1rem;">
      <h1 style="font-size:2rem;color:var(--teal);margin-bottom:.5rem;">
        Welcome to Little Z’s Playhouse Daycare 🌈
      </h1>
      <p class="muted" style="font-size:1.05rem;margin-bottom:1.2rem;">
        Licensed childcare in Farmingdale, NY — nurturing growth from 6 weeks to 5 years old.
      </p>
    <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:.8rem;margin-top:1rem;">
  <a class="btn" data-go href="/contact" style="display:inline-flex;align-items:center;gap:.4rem;">
    🗓️ <span>Book a Tour</span>
  </a>
  <a class="btn" data-go href="tel:+15169127375"
     style="background:var(--teal);display:inline-flex;align-items:center;gap:.4rem;">
    📞 <span>Call / Text 516-912-7375</span>
  </a>
</div>
    </section>

    <div class="grid grid-2">
      <a class="card" href="/about" style="text-decoration:none;">
        <h2>Healthy Meals</h2>
        <p class="muted">Home-cooked and balanced. Common allergies accommodated.</p>
      </a>
      <a class="card" href="/programs" style="text-decoration:none;">
        <h2>Safe Backyard Play</h2>
        <p class="muted">Outdoor time in our dedicated, supervised play area.</p>
      </a>
    </div>
    """
    return render("home", "Home", body)

@app.route("/about")
def about():
    body = """
    <h1>About Us</h1>
    <div class="card">
      <p>We’re a licensed, family-style daycare in Farmingdale. Children learn through play, stories, music, and hands-on activities.</p>
      <p><strong>Spanish-friendly:</strong> We naturally introduce simple Spanish words and songs during the day.</p>
    </div>
    """
    return render("about", "About", body)

@app.route("/programs")
def programs():
    body = """
    <h1>Programs</h1>
    <div class="grid grid-2">
      <div class="card"><h2>Infants (6w–12m)</h2><p>Warm, responsive care with tummy time and sensory play.</p></div>
      <div class="card"><h2>Toddlers (1–3y)</h2><p>Language building, circle time, art, music, and gross motor fun.</p></div>
      <div class="card"><h2>Preschool (3–5y)</h2><p>Pre-K readiness: letters, numbers, crafts, social-emotional learning.</p></div>
      <div class="card"><h2>Schedules</h2><p>Full-time & limited part-time. Ask about early drop-off/late pick-up.</p></div>
    </div>
    """
    return render("programs", "Programs", body)

# -------- Contact (with working honeypot) --------
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        # Honeypot: real users won't fill this hidden field
        if request.form.get("website"):
            return redirect(url_for("thanks"))

        row = [
            datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            request.form.get("name", "").strip(),
            request.form.get("email", "").strip(),
            request.form.get("phone", "").strip(),
            request.form.get("message", "").strip(),
        ]
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)
        return redirect(url_for("thanks"))

    body = """
<h1>Contact Us or Book a Tour</h1>

<div class="card" style="background:#f8fbfd;">
  <strong>Tour Hours (By Appointment Only):</strong><br>
  Monday–Friday <strong>5:15–6:15 p.m.</strong><br>
  Saturday <strong>9:30 a.m.–5:00 p.m.</strong><br>
  <span class="muted">
    Families are welcome to schedule a private visit to see our space and meet the provider. 
    Use the form below to request a tour or send us a message.  
    You may also call or text us directly at <a href="tel:+15169127375">516-912-7375</a>.
  </span>
</div>

<h2 style="color:var(--teal);margin-top:1.5rem;">Send Us a Message</h2>

<form method="post" class="card" autocomplete="on">
  <!-- Honeypot (hidden to humans, visible to bots) -->
  <div style="position:absolute;left:-9999px;top:auto;width:1px;height:1px;overflow:hidden;">
    <label>Website</label>
    <input type="text" name="website" tabindex="-1" autocomplete="off">
  </div>

  <label>Your Name</label>
  <input name="name" required autocomplete="name">

  <label>Email</label>
  <input name="email" type="email" required autocomplete="email">

  <label>Phone</label>
  <input name="phone" autocomplete="tel" pattern="^[0-9+\\-() ]{7,}$" title="Digits, spaces, +, -, ()">

  <label>Message</label>
  <textarea name="message" rows="4" required maxlength="600" 
    placeholder="Please share your child’s age and preferred tour day/time."></textarea>

  <div style="margin-top:.8rem"><button class="btn">Send Message</button></div>
</form>

<p class="muted" style="margin-top:0.5rem;">
  Submissions are securely stored in our system. You’ll receive a follow-up call or email within 1–2 business days.
</p>
"""
    return render("contact", "Contact", body)


@app.route("/thanks")
def thanks():
    body = """
    <section class="hero" style="text-align:center;padding:2rem 1rem;">
      <h1>Thank You! 🎉</h1>
      <p class="muted">We’ve received your message. We’ll reach out soon to confirm your tour or answer any questions.</p>
      <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:.8rem;">
        <a class="btn" href="/contact" data-go>Book a Tour</a>
        <a class="btn" href="tel:+15169127375" data-go style="background:var(--teal);">
          📞 Call / Text 516-912-7375
        </a>
      </div>
    </section>
    """
    return render("thanks", "Thank You", body)

# -------- Feedback: Public --------
def new_feedback_id():
    return datetime.now().strftime("%Y%m%d%H%M%S%f")

def load_feedback():
    rows = []
    if os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            rows = list(r)
    return rows

def save_feedback(rows):
    with open(FEEDBACK_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id","timestamp","name","relationship","rating","comment","can_publish","approved"])
        w.writeheader()
        for row in rows:
            w.writerow(row)

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        fid = new_feedback_id()
        rating = request.form.get("rating","").strip()
        try:
            rating = str(max(1, min(5, int(rating))))
        except:
            rating = "5"
        row = {
            "id": fid,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "name": request.form.get("name","").strip(),
            "relationship": request.form.get("relationship","Parent/Guardian").strip(),
            "rating": rating,
            "comment": request.form.get("comment","").strip(),
            "can_publish": "yes" if request.form.get("can_publish") else "no",
            "approved": "no"
        }
        rows = load_feedback()
        rows.append(row)
        save_feedback(rows)
        flash("Thank you! Your feedback was received.")
        return redirect(url_for("feedback"))
    body = """
    <h1>Leave Feedback</h1>
    <form method="post" class="card">
      <label>Name</label>
      <input name="name" required>

      <label>Relationship</label>
      <select name="relationship">
        <option>Parent</option>
        <option>Guardian</option>
        <option>Relative</option>
        <option>Other</option>
      </select>

      <label>Rating (1–5)</label>
      <select name="rating" required>
        <option value="5">5 - Excellent</option>
        <option value="4">4 - Great</option>
        <option value="3">3 - Good</option>
        <option value="2">2 - Fair</option>
        <option value="1">1 - Poor</option>
      </select>

      <label>Comments</label>
      <textarea name="comment" rows="4" maxlength="800" placeholder="What did you love about Little Z’s?"></textarea>

      <label style="display:flex;align-items:center;gap:.5rem;margin-top:.6rem;">
        <input type="checkbox" name="can_publish"> I give permission to display this review publicly.
      </label>

      <div style="margin-top:.9rem"><button class="btn">Submit Feedback</button></div>
    </form>
    """
    return render("feedback", "Leave Feedback", body)

@app.route("/testimonials")
def testimonials():
    rows = load_feedback()
    approved = [r for r in rows if r.get("approved")=="yes" and r.get("can_publish")=="yes"]
    approved.sort(key=lambda r: r.get("timestamp",""), reverse=True)

    cards = []
    for r in approved:
        try:
            rating_int = int(r.get("rating","0") or 0)
        except:
            rating_int = 0
        stars = "★"*rating_int + "☆"*(5-rating_int)
        cards.append(f"""
          <div class="card">
            <div class="stars">{stars}</div>
            <p style="margin:.4rem 0 0;">{r.get('comment','')}</p>
            <div class="muted" style="margin-top:.4rem;">– {r.get('name','Anonymous')}, {r.get('relationship','Parent')}</div>
          </div>
        """)
    body = f"""
      <h1>Testimonials</h1>
      {''.join(cards) if cards else '<div class="card">No testimonials yet. Be the first to <a href="'+url_for('feedback')+'">leave feedback</a>!</div>'}
    """
    return render("testimonials", "Testimonials", body)

# -------- Admin (secure) --------
def admin_required():
    return session.get("is_admin") is True

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Logged in.")
            dest = request.args.get("next") or url_for("admin_messages")
            return redirect(dest)
        flash("Incorrect password.")
    body = """
    <h1>Admin Login</h1>
    <form method="post" class="card" style="max-width:420px">
      <label>Password</label>
      <input name="password" type="password" required>
      <div style="margin-top:.8rem"><button class="btn">Log In</button></div>
    </form>
    <p class="muted-small">Protected area — authorized staff only.</p>
    """
    return render("admin", "Admin Login", body)

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Logged out.")
    return redirect(url_for("admin_login"))

@app.route("/admin/messages")
def admin_messages():
    if not admin_required():
        return redirect(url_for("admin_login", next=request.path))

    rows = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

    header = rows[0] if rows else ["timestamp","name","email","phone","message"]
    data = rows[1:] if len(rows) > 1 else []

    body = """
    <div class="admin-actions">
      <a class="btn" href="{{ url_for('home') }}">⬅︎ Back to Site</a>
      <a class="btn" href="{{ url_for('admin_feedback') }}" style="background:var(--teal);">Feedback Reviews</a>
      <a class="btn" href="{{ url_for('admin_logout') }}" style="background:#7bc4d4;">Logout</a>
    </div>
    <h1>Messages</h1>
    {% if not data %}
      <div class="card">No submissions yet.</div>
    {% else %}
      <div class="card" style="overflow:auto;">
        <table>
          <thead>
            <tr>{% for h in header %}<th>{{ h }}</th>{% endfor %}</tr>
          </thead>
          <tbody>
            {% for row in data %}
              <tr>{% for col in row %}<td>{{ col }}</td>{% endfor %}</tr>
            {% endfor %}
          </tbody>
        </table>
        <div class="muted-small" style="margin-top:.6rem;">Total: {{ data|length }} messages</div>
      </div>
    {% endif %}
    """
    return render("admin", "Messages", render_template_string(body, header=header, data=data))

@app.route("/admin/feedback", methods=["GET", "POST"])
def admin_feedback():
    if not admin_required():
        return redirect(url_for("admin_login", next=request.path))

    rows = load_feedback()

    if request.method == "POST":
        fid = request.form.get("id","")
        action = request.form.get("action","")
        changed = False
        for r in rows:
            if r.get("id") == fid:
                if action == "approve":
                    r["approved"] = "yes"; changed = True
                elif action == "unapprove":
                    r["approved"] = "no"; changed = True
                elif action == "delete":
                    r["__delete__"] = True; changed = True
                break
        if changed:
            rows = [r for r in rows if not r.get("__delete__")]
            save_feedback(rows)
            flash("Saved.")
        return redirect(url_for("admin_feedback"))

    table_html = """
      <div class="admin-actions">
        <a class="btn" href="{{ url_for('home') }}">⬅︎ Back to Site</a>
        <a class="btn" href="{{ url_for('admin_messages') }}">Contact Messages</a>
        <a class="btn" href="{{ url_for('admin_logout') }}" style="background:#7bc4d4;">Logout</a>
      </div>
      <h1>Feedback Reviews</h1>
    """
    if not rows:
        table_html += '<div class="card">No feedback yet.</div>'
    else:
        table_html += """
        <div class="card" style="overflow:auto;">
          <table>
            <thead>
              <tr>
                <th>Date</th><th>Name</th><th>Relation</th><th>Rating</th><th>Comment</th><th>Can Publish?</th><th>Approved</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
        """
        for r in reversed(rows):
            try:
                ri = int(r.get("rating","0") or 0)
            except:
                ri = 0
            stars = "★"*ri + "☆"*(5-ri)
            table_html += f"""
              <tr>
                <td>{r.get('timestamp','')}</td>
                <td>{r.get('name','')}</td>
                <td>{r.get('relationship','')}</td>
                <td><span class="stars">{stars}</span></td>
                <td>{r.get('comment','')}</td>
                <td>{r.get('can_publish','no')}</td>
                <td>{r.get('approved','no')}</td>
                <td>
                  <form method="post" style="display:inline;">
                    <input type="hidden" name="id" value="{r.get('id','')}">
                    <button class="btn" name="action" value="approve">Approve</button>
                  </form>
                  <form method="post" style="display:inline;">
                    <input type="hidden" name="id" value="{r.get('id','')}">
                    <button class="btn" name="action" value="unapprove">Unapprove</button>
                  </form>
                  <form method="post" style="display:inline;">
                    <input type="hidden" name="id" value="{r.get('id','')}">
                    <button class="btn" name="action" value="delete">Delete</button>
                  </form>
                </td>
              </tr>
            """
        table_html += """
            </tbody>
          </table>
        </div>
        """
    return render("admin", "Feedback Reviews", table_html)

# -------- Auto-pick free port + Pythonista-friendly run --------
@app.route("/reviews")
def reviews():
    return """
    <html>
      <head>
        <title>Little Z's Reviews</title>
        <style>
          body { font-family: Arial; text-align: center; margin-top: 60px; }
          a.button {
              background-color: #4285F4;
              color: white;
              padding: 14px 22px;
              text-decoration: none;
              border-radius: 6px;
              font-size: 18px;
          }
          a.button:hover { background-color: #3367D6; }
        </style>
      </head>
      <body>
        <h2>What Our Families Say 💕</h2>
        <p>Click below to read our Google Reviews!</p>
        <a class="button" href="https://maps.app.goo.gl/Dx3Nvx57hsTjAddr6?g_st=ipc" 
           target="_blank" rel="noopener">
          See Reviews on Google
        </a>
      </body>
    </html>
    """
def find_free_port(start=PREFERRED_PORT_START, end=PREFERRED_PORT_END):
    for p in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", p))
                return p
            except OSError:
                continue
    return None

if __name__ == "__main__":
    PORT = find_free_port(PREFERRED_PORT_START, PREFERRED_PORT_END) or PREFERRED_PORT_START
    try:
        lan_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        lan_ip = "127.0.0.1"

    print(f"\nOpen on this iPhone:  http://127.0.0.1:{PORT}")
    print(f"Open from same Wi-Fi: http://{lan_ip}:{PORT}\n")

    # Pythonista best practices:
    # - use_reloader=False prevents ghost process that keeps the port busy
    # - threaded=True allows quick taps without choking
    app.run(host=HOST, port=PORT, debug=False, threaded=True, use_reloader=False)
