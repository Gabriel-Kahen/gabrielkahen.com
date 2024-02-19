tabs.style.height = (screen.height * .042) + "px";
url.style.height = (screen.height * .041) + "px";
bookmarks.style.height = (screen.height * .035) + "px";
var imgHeight = (screen.height * .05)
tabimg.style.height = imgHeight + "px";

var imgWidth = imgHeight * 1942 / 36;

gabrielkahen.style.bottom = (screen.height * .05)/8 + "px";
LinkedIn.style.bottom = (screen.height * .05)/8 + 2 + "px";
GitHub.style.bottom = (screen.height * .05)/8 + 2 + "px";
Email.style.bottom = (screen.height * .05)/8 + 2 + "px";

gabrielkahen.style.left = 20/2570 * imgWidth + "px";
LinkedIn.style.left = 250/2570 * imgWidth + "px";
GitHub.style.left = 491/2570 * imgWidth + "px";
Email.style.left = 728/2570 * imgWidth + "px";

gabrielkahen.style.width = imgWidth * .085 + "px"
LinkedIn.style.width = imgWidth * .085 + "px"
GitHub.style.width = imgWidth * .085 + "px"
Email.style.width = imgWidth * .085 + "px"

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
