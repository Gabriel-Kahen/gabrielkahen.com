tabs.style.height = (screen.height * .042) + "px";
url.style.height = (screen.height * .041) + "px";
bookmarks.style.height = (screen.height * .035) + "px";
tabimg.style.height = (screen.height * .05) + "px";

gabrielkahen.style.bottom = (screen.height * .05)/8 + "px";
LinkedIn.style.bottom = (screen.height * .05)/8 + "px";
GitHub.style.bottom = (screen.height * .05)/8 + "px";
Email.style.bottom = (screen.height * .05)/8 + "px";

gabrielkahen.style.left = 20 + "px";
LinkedIn.style.left = 13 + 237 * 1 + "px";
GitHub.style.left = 17 + 237 * 2 + "px";
Email.style.left = 17 + 237 * 3 + "px";

function reload(){
    location.reload();
}

function linkedin(){
    window.open("https://www.linkedin.com/in/gabrielkahen/");
}

function github(){
    window.open("https://github.com/Gabriel-Kahen");
}

function email(){
    window.open("mailto:gabekahen@gmail.com");
}