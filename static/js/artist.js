function favorite_artist(artist_id) {
    fetch(`/favorites/artist/${artist_id}`, {
        method: 'POST'
    }).then(res => {
        if (res.redirected) {
            window.location = add_url_param(res.url, 'redir', window.location.pathname);
        } else if (res.ok) {
            location.reload();
        } else {
            alert('Error 001 - could not save favorite');
        }
    });
}

function unfavorite_artist(artist_id) {
    fetch(`/favorites/artist/${artist_id}`, {
        method: "DELETE"
    }).then(res => {
        if (res.redirected) {
            window.location = add_url_param(res.url, 'redir', window.location.pathname);;
        } else if (res.ok) {
            location.reload();
        } else {
            alert('Error 002 - could not remove favorite');
        }
    });
}
