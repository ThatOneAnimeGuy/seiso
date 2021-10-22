function onclick_change_display_name(show_editor) {
    var display = document.getElementById('show_display_name');
    var edit = document.getElementById('edit_display_name');
    if (show_editor) {
        removeClass(edit, 'hidden');
        addClass(display, 'hidden');
    } else {
        addClass(edit, 'hidden');
        removeClass(display, 'hidden');
    }
}

function onclick_delete_auto_import_session(service, event) {
    var data = new FormData();
    data.append('service', service);
    fetch('/api/account/auto_imports', {
        method: 'DELETE',
        body: (new URLSearchParams(data))
    }).then(function(resp) {
        if (resp.status == 204) {
            event.target.parentNode.parentNode.remove();
        } else {
            throw new Error();
        }
    }).catch(function(err) {
        alert('Error deleting session. Please try again.')
    });
}
