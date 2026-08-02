CORE_BOT_SCRIPT = """
(function() {
    'use strict';
    console.log("🤖 [KICK BOT VIP ENGINE] Active & Protected!");
    
    // Auto-Claim & Follow Engine
    setInterval(() => {
        if (window.location.href.includes('/drops/inventory')) {
            const elements = document.querySelectorAll('button, a');
            elements.forEach(el => {
                const txt = (el.innerText || '').toLowerCase();
                if ((txt.includes('claim') || txt.includes('klaim')) && !el.disabled) {
                    el.click();
                    console.log("🎉 [KICK BOT] Auto Claim Clicked!");
                }
            });
        }
    }, 5000);
})();
"""

def generate_encrypted_payload(license_key: str):
    return f"window.KICK_BOT_LICENSE = '{license_key}';\n" + CORE_BOT_SCRIPT
