// hr3000.de/registrieren: Firma selbst registrieren (POST /api/public/signup).
// Die Adresse wird aus dem Firmennamen vorgeschlagen (bis man sie selbst ändert) und live
// geprüft (GET /api/public/subdomain-available). Geprüft wird alles noch einmal im Backend.
(function () {
  'use strict'

  var LABEL = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/
  var BASE = window.location.hostname.replace(/^www\./, '')

  var form = document.getElementById('signup-form')
  var company = document.getElementById('company')
  var subdomain = document.getElementById('subdomain')
  var status = document.getElementById('subdomain-status')
  var contact = document.getElementById('contact')
  var email = document.getElementById('email')
  var password = document.getElementById('password')
  var password2 = document.getElementById('password2')
  var honeypot = document.getElementById('website')
  var isBusiness = document.getElementById('is-business')
  var acceptTerms = document.getElementById('accept-terms')
  var submit = document.getElementById('submit')
  var message = document.getElementById('message')
  var suffix = document.getElementById('domain-suffix')

  if (suffix && BASE.indexOf('.') > 0) suffix.textContent = '.' + BASE

  var DEFAULT_HINT = status.textContent
  var userEditedSubdomain = false
  var checkTimer = null
  var lastChecked = null
  var available = null

  /** "Bäckerei Müller & Söhne GmbH" -> "baeckerei-mueller-und-soehne" */
  function slugify(value) {
    var v = String(value || '').toLowerCase()
      .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
      .replace(/&/g, ' und ')
    if (v.normalize) v = v.normalize('NFKD').replace(/[̀-ͯ]/g, '')
    v = v.replace(/\b(gmbh|mbh|ug|ag|kg|ohg|gbr|co|haftungsbeschraenkt|e\.?\s?k\.?|e\.?\s?v\.?)\b/g, ' ')
    v = v.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').replace(/-{2,}/g, '-')
    return v.slice(0, 63).replace(/-+$/, '')
  }

  function setStatus(text, kind) {
    status.textContent = text
    status.className = 'field-hint' + (kind ? ' ' + kind : '')
  }

  function show(text, isError) {
    message.textContent = text
    message.className = 'message' + (isError ? ' error' : '')
  }

  function checkAvailability() {
    var value = subdomain.value
    available = null
    if (!value) { setStatus(DEFAULT_HINT, ''); return }
    if (!LABEL.test(value)) {
      setStatus('Nur Kleinbuchstaben, Ziffern und Bindestriche (nicht am Anfang oder Ende).', 'error')
      available = false
      return
    }
    lastChecked = value
    setStatus('Prüfe …', '')
    fetch('/api/public/subdomain-available?subdomain=' + encodeURIComponent(value), {
      headers: { Accept: 'application/json' },
      credentials: 'omit',
    })
      .then(function (r) { return r.json().then(function (b) { return { status: r.status, body: b } }) })
      .then(function (result) {
        if (subdomain.value !== lastChecked) return // inzwischen weitergetippt
        if (result.status === 200 && result.body.available) {
          available = true
          setStatus('✓ ' + value + '.' + BASE + ' ist frei.', 'ok')
        } else if (result.status === 200) {
          available = false
          setStatus(result.body.reason === 'RESERVED' ? 'Diese Adresse ist reserviert.' : 'Diese Adresse ist leider schon vergeben.', 'error')
        } else if (result.status === 404) {
          setStatus('Die Registrierung ist derzeit nicht möglich.', 'error')
        } else {
          setStatus(DEFAULT_HINT, '')
        }
      })
      .catch(function () { setStatus(DEFAULT_HINT, '') })
  }

  function scheduleCheck() {
    clearTimeout(checkTimer)
    checkTimer = setTimeout(checkAvailability, 400)
  }

  company.addEventListener('input', function () {
    if (userEditedSubdomain) return
    subdomain.value = slugify(company.value)
    scheduleCheck()
  })

  subdomain.addEventListener('input', function () {
    userEditedSubdomain = subdomain.value !== ''
    var cleaned = subdomain.value.toLowerCase().replace(/\s+/g, '-')
    if (cleaned !== subdomain.value) subdomain.value = cleaned
    scheduleCheck()
  })

  function fail(text, field) {
    show(text, true)
    if (field) field.focus()
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault()
    if (company.value.trim().length < 2) return fail('Bitte gib den Namen deiner Firma ein.', company)
    if (!LABEL.test(subdomain.value)) return fail('Bitte wähle eine gültige Adresse.', subdomain)
    if (available === false) return fail('Diese Adresse ist nicht verfügbar – bitte wähle eine andere.', subdomain)
    if (contact.value.trim().length < 2) return fail('Bitte gib deinen Namen ein.', contact)
    if (!email.value || !email.checkValidity()) return fail('Bitte gib eine gültige E-Mail-Adresse ein.', email)
    if (password.value.length < 10) return fail('Das Passwort muss mindestens 10 Zeichen haben.', password)
    if (password.value !== password2.value) return fail('Die Passwörter stimmen nicht überein.', password2)
    if (!isBusiness.checked) return fail('HR3000 ist ausschließlich für Unternehmen.', isBusiness)
    if (!acceptTerms.checked) return fail('Bitte akzeptiere die Nutzungsbedingungen und den AV-Vertrag.', acceptTerms)

    submit.disabled = true
    show('Deine Firma wird eingerichtet …', false)
    fetch('/api/public/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      credentials: 'omit',
      body: JSON.stringify({
        company_name: company.value.trim(),
        subdomain: subdomain.value,
        contact_name: contact.value.trim(),
        email: email.value.trim(),
        password: password.value,
        is_business: true,
        accept_terms: true,
        website: honeypot.value,
      }),
    })
      .then(function (r) { return r.json().catch(function () { return {} }).then(function (b) { return { status: r.status, body: b } }) })
      .then(function (result) {
        if (result.status === 201 && result.body.login_url) {
          var url = result.body.login_url
          document.getElementById('done-url').textContent = url.replace(/^https:\/\//, '').replace(/\/$/, '')
          document.getElementById('done-url').href = url
          document.getElementById('done-login').href = url
          document.getElementById('done-kiosk').textContent = 'kiosk.' + result.body.subdomain + '.' + BASE
          document.getElementById('signup-form-view').hidden = true
          document.getElementById('signup-done-view').hidden = false
          window.scrollTo(0, 0)
          return
        }
        submit.disabled = false
        var code = result.body && result.body.code
        if (result.status === 409) { available = false; fail('Diese Adresse ist leider schon vergeben – bitte wähle eine andere.', subdomain) }
        else if (result.status === 429) fail('Heute sind von hier keine weiteren Registrierungen möglich. Bitte versuch es morgen erneut.')
        else if (result.status === 404 && code === 'SIGNUP_DISABLED') fail('Die Registrierung ist derzeit nicht möglich.')
        else if (result.status === 422) fail('Bitte prüf deine Angaben (Adresse, E-Mail, Passwort mit mindestens 10 Zeichen).')
        else fail('Das hat nicht geklappt. Bitte versuch es gleich noch einmal.')
      })
      .catch(function () {
        submit.disabled = false
        fail('Keine Verbindung. Bitte prüf deine Internetverbindung.')
      })
  })
})()
