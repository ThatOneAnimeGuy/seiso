function on_change_favorite_type(target) {
    if (target) {
        var new_type = target.value;
        if (new_type) {
            window.location = '/favorites?type=' + new_type;
        }
    }
}

function on_change_filters(field, target) {
    if (target) {
        var value = target.value;
        var query_string = window.location.search;
        var url_params = new URLSearchParams(query_string);
        url_params.set(field, value);
        window.location.search = url_params.toString();
    }
}
