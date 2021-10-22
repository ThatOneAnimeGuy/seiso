function flag_post(post_id) {
    if (confirm('Are you sure you want to flag this post for reimport? Only flag this post if it is missing data or has something wrong with it.')) {
        fetch(`/post/flag/${post_id}`, { method: 'post' })
        .error(err => alert('Error 003 - could not flag post'));
    }
}

function favorite_post(post_id) {
    fetch(`/favorites/post/${post_id}`, {
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

function unfavorite_post(post_id) {
    fetch(`/favorites/post/${post_id}`, {
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
