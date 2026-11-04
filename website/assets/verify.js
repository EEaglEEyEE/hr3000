// hr3000.de/bestaetigen/#token=…: Bestätigungslink aus der Registrierungsmail einlösen
// (POST /api/public/verify-email) und dann zur Anmeldung der Firma weiterleiten.
(function () {
  'use strict'
  var message = document.getElementById('verify-message')
  var login = document.getElementById('verify-login')
  var match = window.location.hash.match(/token=([A-Za-z0-9_-]+)/)
  // Token nicht in Adresszeile und Verlauf stehen lassen.
  if (match) window.history.replaceState(null, '', window.location.pathname)

  function show(text, isError) {
    message.textContent = text
    message.className = 'message' + (isError ? ' error' : '')
  }

  if (!match) {
    show('Der Link ist unvollständig. Bitte öffne ihn direkt aus der E-Mail.', true)
    return
  }

  fetch('/api/public/verify-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    credentials: 'omit',
    body: JSON.stringify({ token: match[1] }),
  })
    .then(function (r) { return r.json().catch(function () { return {} }).then(function (b) { return { status: r.status, body: b } }) })
    .then(function (result) {
      if (result.status === 200 && result.body.login_url) {
        show('Danke! Deine E-Mail-Adresse ist bestätigt – du kannst dich jetzt anmelden.', false)
        login.href = result.body.login_url
        login.hidden = false
        return
      }
      if (result.status === 429) show('Zu viele Versuche. Bitte warte ein paar Minuten.', true)
      else show('Der Link ist ungültig oder abgelaufen. Melde dich einfach an – wir schicken dir dann einen neuen.', true)
      login.hidden = false
    })
    .catch(function () { show('Keine Verbindung. Bitte prüf deine Internetverbindung.', true) })
})()
