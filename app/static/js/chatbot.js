document.addEventListener('DOMContentLoaded', function() {
    function ocultarBotonTema() { var b = document.getElementById('btnTema'); if(b) b.style.display = 'none'; }
    ocultarBotonTema();
    let btnMic = document.createElement('button'); btnMic.className = 'chatbot-btn'; btnMic.innerHTML = '&#127908;'; btnMic.title = 'Decir "Hey Luz" o tocar para hablar'; btnMic.style.bottom = '90px'; btnMic.onclick = function() { iniciarEscucha(); }; document.body.appendChild(btnMic);
    let btnChat = document.createElement('button'); btnChat.className = 'chatbot-btn'; btnChat.innerHTML = '&#128172;'; btnChat.title = 'Chatear con Luz'; btnChat.style.bottom = '150px'; btnChat.onclick = toggleChat; document.body.appendChild(btnChat);
    let chatWin = document.createElement('div'); chatWin.className = 'chat-window'; chatWin.id = 'chatWindow'; chatWin.innerHTML = '<div class="chat-header">&#129302; Luz - Asistente Virtual <span style="float:right;cursor:pointer" onclick="toggleChat()">&#10006;</span></div><div class="chat-body" id="chatBody"><div class="msg bot">&#161;Hola! Soy <strong>Luz</strong>, tu asistente. Dime "Hey Luz" y tu comando.</div></div><div class="chat-input"><input type="text" id="chatInput" placeholder="Escribe..."><button onclick="enviarMensaje()">Enviar</button><button onclick="iniciarEscucha()" title="Hablar">&#127908;</button></div>'; document.body.appendChild(chatWin);
    document.getElementById('chatInput').addEventListener('keypress', function(e) { if (e.key === 'Enter') enviarMensaje(); });
    var logoBarra = document.querySelector('.barra-superior a');
    if (logoBarra) { logoBarra.style.cursor = 'pointer'; logoBarra.title = 'Tocar para cambiar tema claro/oscuro'; logoBarra.addEventListener('click', function(e) { e.preventDefault(); cambiarTemaGlobal(); }); }
    aplicarTemaGuardado();
});
function cambiarTemaGlobal() {
    var body = document.body; var nuevoTema;
    if (body.classList.contains('modo-oscuro')) { body.classList.remove('modo-oscuro'); nuevoTema = 'claro'; }
    else { body.classList.add('modo-oscuro'); nuevoTema = 'oscuro'; }
    localStorage.setItem('tema', nuevoTema);
    fetch('/toggle_tema', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tema: nuevoTema}) }).catch(function() {});
}
function aplicarTemaGuardado() { var t = localStorage.getItem('tema'); if (t === 'oscuro') document.body.classList.add('modo-oscuro'); else if (t === 'claro') document.body.classList.remove('modo-oscuro'); }
function toggleChat() { let w = document.getElementById('chatWindow'); w.style.display = w.style.display === 'flex' ? 'none' : 'flex'; }
function enviarMensaje(textoPersonalizado) {
    let input = document.getElementById('chatInput'); let pregunta = textoPersonalizado || input.value.trim();
    if (!pregunta) pregunta = 'ayuda'; let body = document.getElementById('chatBody');
    body.innerHTML += '<div class="msg user">' + pregunta + '</div>'; if (!textoPersonalizado) input.value = '';
    body.scrollTop = body.scrollHeight;
    fetch('/api/chatbot', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({pregunta: pregunta}) })
    .then(r => r.json()).then(data => { body.innerHTML += '<div class="msg bot">' + data.respuesta + '</div>'; body.scrollTop = body.scrollHeight;
        if (data.respuesta && 'speechSynthesis' in window) { let u = new SpeechSynthesisUtterance(data.respuesta); u.lang = 'es-ES'; speechSynthesis.speak(u); } });
}
function iniciarEscucha() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) { alert('Reconocimiento de voz no soportado.'); return; }
    let SR = window.SpeechRecognition || window.webkitSpeechRecognition; let rec = new SR(); rec.lang = 'es-ES'; rec.interimResults = false;
    let btn = document.querySelector('.chatbot-btn[title*="Hey Luz"]'); if (btn) btn.innerHTML = '&#128308;';
    rec.onresult = function(e) { let texto = e.results[0][0].transcript; if (btn) btn.innerHTML = '&#127908;'; enviarMensaje(texto); };
    rec.onerror = function() { if (btn) btn.innerHTML = '&#127908;'; }; rec.start();
                                                                                                                                                           }
