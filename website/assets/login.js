// hr3000.de/login: Firmen-Kürzel eingeben -> Server prüft, ob es die Firma gibt
// (GET /api/public/tenant-lookup) -> Weiterleitung auf https://<firma>.hr3000.de/.
// "Merken" speichert nur das Kürzel im localStorage dieses Browsers (kein Cookie).
(function () {
  'use strict'

  var STORAGE_KEY = 'hr3000.firma'
  var LABEL = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/
  // Plattform-Domain = aktuelle Adresse ohne "www." (z. B. hr3000.de)
  var BASE = window.location.hostname.replace(/^www\./, '')

  var form = document.getElementById('login-form')
  var input = document.getElementById('firma')
  var remember = document.getElementById('remember')
  var message = document.getElementById('message')
  var submit = document.getElementById('submit')
  var suffix = document.getElementById('domain-suffix')

  if (suffix && BASE.indexOf('.') > 0) suffix.textContent = '.' + BASE

  /** Nimmt auch ganze Adressen an: "https://Firma.hr3000.de/login", "kiosk.firma.hr3000.de". */
  function normalize(value) {
    var v = String(value || '').trim().toLowerCase()
    v = v.replace(/^[a-z]+:\/\//, '').split(/[/?#]/)[0].replace(/\.$/, '')
    var tail = '.' + BASE
    if (v.length > tail.length && v.slice(-tail.length) === tail) v = v.slice(0, -tail.length)
    if (v.indexOf('kiosk.') === 0) v = v.slice('kiosk.'.length)
    return v
  }

  function storage(action, value) {
    try {
      if (action === 'get') return window.localStorage.getItem(STORAGE_KEY)
      if (action === 'set') window.localStorage.setItem(STORAGE_KEY, value)
      if (action === 'remove') window.localStorage.removeItem(STORAGE_KEY)
    } catch (e) {
      /* privater Modus o. ä.: dann eben ohne Merken */
    }
    return null
  }

  function show(text, isError) {
    message.textContent = text
    message.className = 'message' + (isError ? ' error' : '')
  }

  var saved = storage('get')
  if (saved && LABEL.test(saved)) {
    input.value = saved
    remember.checked = true
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault()
    var firma = normalize(input.value)
    if (!firma) {
      show('Bitte gib die Adresse deiner Firma ein.', true)
      input.focus()
      return
    }
    if (!LABEL.test(firma)) {
      show('Die Adresse darf nur Buchstaben, Ziffern und Bindestriche enthalten.', true)
      input.focus()
      return
    }
    input.value = firma
    submit.disabled = true
    show('Einen Moment …', false)

    fetch('/api/public/tenant-lookup?subdomain=' + encodeURIComponent(firma), {
      headers: { Accept: 'application/json' },
      credentials: 'omit',
    })
      .then(function (response) {
        return response.json().catch(function () { return {} }).then(function (body) {
          return { status: response.status, body: body }
        })
      })
      .then(function (result) {
        if (result.status === 200 && result.body.login_url) {
          if (remember.checked) storage('set', firma)
          else storage('remove')
          show('Weiter zu ' + firma + '.' + BASE + ' …', false)
          window.location.assign(result.body.login_url)
          return
        }
        submit.disabled = false
        if (result.status === 404) show('Zu „' + firma + '“ haben wir keine Firma gefunden. Bitte prüf die Schreibweise.', true)
        else if (result.status === 429) show('Zu viele Versuche. Bitte warte ein paar Minuten.', true)
        else show('Das hat nicht geklappt. Bitte versuch es gleich noch einmal.', true)
      })
      .catch(function () {
        submit.disabled = false
        show('Keine Verbindung. Bitte prüf deine Internetverbindung.', true)
      })
  })
})()
