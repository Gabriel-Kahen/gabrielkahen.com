/* tab */

var screenHeight = screen.height;
var screenWidth = screen.width;
var imgHeight = (screenHeight * .05)
var imgWidth = imgHeight * 1942 / 36;

tabs.style.height = (screenHeight * .042) + "px";
url.style.height = (screenHeight * .041) + "px";
bookmarks.style.height = (screenHeight * .035) + "px";
tabimg.style.height = imgHeight + "px";

gabrielkahen.style.left = 20/2570 * imgWidth + "px";
LinkedIn.style.left = 250/2570 * imgWidth + "px";
GitHub.style.left = 491/2570 * imgWidth + "px";
Email.style.left = 728/2570 * imgWidth + "px";

document.querySelectorAll('.tab').forEach(element => {
    element.style.bottom = (screenHeight * 0.05) / 8 + 'px';
    element.style.width = imgWidth * .085 + "px";
});

/* url */

var size = imgWidth * .0053;
var spacing = imgWidth * .006;

document.querySelectorAll('.mod').forEach(element => {
    element.style.width = size + spacing + "px";
    element.style.height = size + spacing + "px";
    element.style.bottom =  screenHeight * .0065 + "px";
});

document.querySelectorAll('.modImg').forEach(element => {
    element.style.width = size + "px";
    element.style.height = size + "px";
});

account.style.width = (size + spacing) + "px";
account.style.height = (size + spacing) + "px";
account.style.bottom =  screenHeight * .0058 + "px";
accountImg.style.width = size * 1.5 + "px";
accountImg.style.height = size * 1.5 + "px";

arrow_back.style.left = imgWidth * .0037 + "px";
arrow_forward.style.left = imgWidth * .0161 + "px";
refresh.style.left = imgWidth * .028 + "px";

tripledots.style.right = imgWidth * .0034 + "px";
account.style.right = imgWidth * .0155 + "px";

urlbar.style.height = (screenHeight * .041) * .65 + "px";
urlbar.style.bottom = screenHeight * .004 + "px"
urlbar.style.left = imgWidth * .042 + "px";
resizeURL();

window.addEventListener("resize", resizeURL);

document.getElementById('urlbar').addEventListener('keypress', function(event) {
    if (event.key === 'Enter') {
      var inputValue = event.target.value;
      search(inputValue);
    }
  });

function search(input){
    window.open("https://www.google.com/search?q=" + input);
}

function resizeURL(){
    urlbar.style.width = (window.innerWidth) - (screenWidth * .077 + 100) + "px";
}

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

function tripledot(){
    location.reload();
}
