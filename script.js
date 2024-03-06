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

/* bookmarks */

document.querySelectorAll('.bookmark').forEach(element => {
    element.style.height = screenHeight * .025 + "px";
    element.style.bottom = screenHeight * .005 + "px";

});

gabelogo.style.height = screenHeight * .08 + "px";
gabelogo.style.marginTop = screenHeight * .2 + "px";

/* body */

orangelogo.style.right = imgWidth * .005 + "px";
orangelogo.style.top = screenHeight * .128 + "px";
orangelogo.style.width = imgWidth * .017 + "px";
orangelogo.style.height = imgWidth * .017 + "px";

dotsarray.style.right = imgWidth * .025 + "px";
dotsarray.style.top = screenHeight * .128 + "px";
dotsarray.style.width = imgWidth * .017 + "px";
dotsarray.style.height = imgWidth * .017 + "px";

bodyGmail.style.right = imgWidth * .045 + "px";
bodyGmail.style.top = screenHeight * .14 + "px";
bodyGmail.style.width = imgWidth * .017 + "px";
bodyGmail.style.height = imgWidth * .017 * .5 + "px";

/* search bar */

dropdown.style.marginTop = screenHeight * .07 + "px";
dropdown.style.height = screenHeight * .04 + "px";
resizeSearch();



/* functions */

window.addEventListener("resize", resizeURL);
window.addEventListener("resize", resizeSearch);


document.getElementById('urlbar').addEventListener('keypress', function(event) {
    if (event.key === 'Enter') {
      var inputValue = event.target.value;
      search(inputValue);
    }
  });

  document.getElementById('textInput').addEventListener('keypress', function(event) {
    if (event.key === 'Enter') {
      var inputValue = event.target.value;
      search(inputValue);
    }
  });

function search(input){
    window.open("https://www.google.com/search?q=" + input);
}

function resizeSearch(){
    var ratio = window.innerWidth / window.innerHeight;
    if(ratio > 1){
        dropdown.style.width = 550 + "px";
    }
    else{
        var urlbarElement = document.getElementById("urlbar");
        var computedStyleLeft = window.getComputedStyle(urlbarElement);
        var left = computedStyleLeft.getPropertyValue("left");
        var leftValue = parseFloat(left);
        var urlWidth = (window.innerWidth - leftValue * 1.8);
        dropdown.style.width = urlWidth + "px";
    }
}

function resizeURL(){
    var urlbarElement = document.getElementById("urlbar");
    var computedStyleLeft = window.getComputedStyle(urlbarElement);
    var left = computedStyleLeft.getPropertyValue("left");
    var leftValue = parseFloat(left);
    var urlWidth = (window.innerWidth - leftValue * 2);
    urlbar.style.width = urlWidth + "px";

}

function reload(){
    location.reload();
}

function openLinkedin(){
    window.open("https://www.linkedin.com/in/gabrielkahen/");
}

function openGithub(){
    window.open("https://github.com/Gabriel-Kahen");
}

function openEmail(){
    window.open("mailto:gabekahen@gmail.com");
}

function openTripledots(){
    location.reload();
}

function openTwitter(){
    window.open("https://twitter.com/gabekahen_");
}

function openWikirace(){
    window.open("https://gabriel-kahen.github.io/wikirace-prompt-generator/");
}

function openMonkeyarchive(){
    window.open("http://monkeyarchive.com");
}

/* tooltips */

const tooltipButtons = document.querySelectorAll('.hasTooltip');
const tooltip = document.getElementById('tooltip');

let timeout;

tooltipButtons.forEach(button => {
    button.addEventListener('mouseenter', () => {
      timeout = setTimeout(() => {
        tooltip.textContent = button.dataset.tooltip;
        tooltip.classList.add('active');
        const rect = button.getBoundingClientRect();
        tooltip.style.top = rect.bottom + 'px';
        tooltip.style.left = rect.left + 'px';
      }, 500);
    });
  
    button.addEventListener('mouseleave', () => {
      clearTimeout(timeout);
      tooltip.classList.remove('active');
    });
  });

  /* search bar */

  var dropdownOptions = document.getElementById("dropdownOptions");

  function toggleDropdown(event) {
    dropdownOptions.style.borderRadius = "0 0 16px 16px";
    dropdown.style.borderRadius = "16px 16px 0 0";

    event.stopPropagation();
    if (dropdownOptions.style.display === "none" || dropdownOptions.style.display === "") {
      dropdownOptions.style.display = "block";
      document.addEventListener("click", closeDropdown);
    } else {
      dropdownOptions.style.display = "none";
      document.removeEventListener("click", closeDropdown);
    }
  }

  function selectOption(option) {
    document.getElementById("textInput").value = option;
    document.getElementById("dropdownOptions").style.display = "none";
    document.removeEventListener("click", closeDropdown);
  }

  function closeDropdown(event) {
    dropdown.style.borderRadius = "16px";
    dropdown.style.borderBottomColor = "#CCC";
    var dropdownOptions = document.getElementById("dropdownOptions");
    if (!dropdownOptions.contains(event.target)) {
      dropdownOptions.style.display = "none";
      document.removeEventListener("click", closeDropdown);
    }
  }
  