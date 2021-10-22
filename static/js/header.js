function toggle_dropdown() {
    var nav = document.getElementById("header");
    if (nav.className === "header") {
        nav.className += " responsive";
        document.body.className = "no-overflow";
    } else {
        nav.className = "header";
        document.body.className = "";
    }
}

function toggle_content(elem) {
    var content = elem.querySelector('.dropdown-content');
    if (content) {
        if (content.className.includes('mobile-dropdown-hidden')) {
            content.className = content.className.replace('mobile-dropdown-hidden', 'mobile-dropdown-expanded');
        } else if (content.className.includes('mobile-dropdown-expanded')) {
            content.className = content.className.replace('mobile-dropdown-expanded', 'mobile-dropdown-hidden');
        }
    }
}
