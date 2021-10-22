function add_url_param(url, param_name, param_value) {
    var newURL = new URL(url);
    newURL.searchParams.set(param_name, param_value);
    return newURL.toString();
}

function addClass(e, c) {
    var cl = [];
    if (e) {
        cl = e.classList;
    } else {
        return;
    }
    if (cl.contains(c)) {
        return;
    }
    cl.add(c);
}

function removeClass(e, c){
    var cl = [];
    if(e) {
        cl = e.classList
    } else {
        return;
    }
    if (cl.contains(c)) {
        cl.remove(c);
    }
}
