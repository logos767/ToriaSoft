# TODO

- [ ] Modify `app/templates/base.html`:
    - [ ] Add a `<style>` tag in the `<head>` section of `app/templates/base.html` and include a media query to target small screens (e.g., `max-width: 768px`).
    - [ ] Inside the media query, wrap the user info (name, role), notification bell, and logout link in a `div` with the ID `user-menu`.
    - [ ] Add an `<i>` tag with a user icon class (e.g., `fas fa-user-circle`) inside the `user-menu` div.
    - [ ] Use Tailwind CSS classes to style the `user-menu` div as a circular icon with a background color and rounded corners on small screens.
    - [ ] Hide the user info, notification bell, and logout link by default on small screens using the `hidden` class.
    - [ ] Move the notification dropdown code inside the `user-menu` div.
    - [ ] Style the notification list as a submenu using CSS.
    - [ ] Use JavaScript to toggle the visibility of the submenu when the notification bell is clicked (or tapped).
- [ ] Add a `<script>` tag to include JavaScript code to handle the click event on the user icon and toggle the visibility of the user menu elements.
