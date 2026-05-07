// example from github guy from italy nail something

const ctx = document.getElementById("myChart");
const myChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 
		  datasets: [{
        borderWidth: 2,
		  	data: [90, 91, 95, 92, 91, 89, 90, 91, 95, 92, 91, 89],
        borderColor: 'red'
		  }]
    },
    options: {
      responsive: true,
      scales: {
        y: {
          beginAtZero: true,
        }
      },
      plugins: {
        legend:  {
           display: false,
        },
				annotation: {
					annotations: {
						box: {
              type: 'box',
              drawTime: 'beforeDraw',
              yMin: 40,
              yMax: 60,
              backgroundColor: 'rgb(207, 219, 225)',
              borderWidth: 0,
              enter() {
                console.log("ENTER!");
              },
              leave() {
                console.log("LEAVE!");
              },
						},
					},
        },
      },
   }
});
function triggerEvent(chart, point){
  const node = chart.canvas;
  const rect = node.getBoundingClientRect();
  const event = new MouseEvent('mousemove', {
    clientX: rect.left + point.x,
    clientY: rect.top + point.y,
    cancelable: true,
    bubbles: true,
    view: window
  });
  node.dispatchEvent(event);
}
document.getElementById('enter').addEventListener('click', function() {
  const area = myChart.chartArea;
  const point = {
    x: area.left + area.width / 2,
    y: area.top + area.height / 2
  };
  triggerEvent(myChart, point);
});
document.getElementById('leave').addEventListener('click', function() {
  const point = {
    x: 0,
    y: 0
  };
  triggerEvent(myChart, point);
});