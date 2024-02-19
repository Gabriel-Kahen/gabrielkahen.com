tabs.style.height = (screen.height * .042) + "px";
url.style.height = (screen.height * .041) + "px";
bookmarks.style.height = (screen.height * .035) + "px";
tabimg.style.height = (screen.height * .05) + "px";

gabrielkahen.style.bottom = (screen.height * .05)/8 + "px";
LinkedIn.style.bottom = (screen.height * .05)/8 + "px";
GitHub.style.bottom = (screen.height * .05)/8 + "px";
Email.style.bottom = (screen.height * .05)/8 + "px";

gabrielkahen.style.left = 20/1472 * screen.width + "px";
LinkedIn.style.left = 250/1472 * screen.width + "px";
GitHub.style.left = 491/1472 * screen.width + "px";
Email.style.left = 728/1472 * screen.width + "px";

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
