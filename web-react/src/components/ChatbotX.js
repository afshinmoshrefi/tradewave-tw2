import React, { useState, useContext } from 'react';
import { UserContext } from './UserContext';
import { appserverURL,trend_chart_left_gap_days,incrementDate } from './Common';

// function Chatbot() {
const Chatbot = (props) => {

  const { token, resourceObj } = useContext(UserContext);
  const asURL = appserverURL();
  const baseURL = `${asURL}/chatbot/chat?token=${token}`;

  const [messages, setMessages] = useState([]);
  const [userInput, setUserInput] = useState('');
  //--------------------------------------------------------------------------------------------------------
  const displayMessage = (role, text, isHtml = false) => {
    setMessages((prev) => [...prev, { role, text, isHtml }]);
  };
  //--------------------------------------------------------------------------------------------------------
  const handleSend = () => {
    if (!userInput.trim()) return;

    displayMessage('user', userInput);

    fetch(baseURL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: userInput }),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        return response.json();
      })
      .then((data) => {
        const isHtml = /<\/?[a-z][\s\S]*>/i.test(data.reply); // Detects if the response is HTML
        displayMessage('bot', data.reply, isHtml);
      })
      .catch((err) => {
        displayMessage('bot', `Error occurred: ${err.message}`);
      });

    setUserInput('');
  };
  //--------------------------------------------------------------------------------------------------------
  const handleKeyDown = (event) => {
    if (event.key === 'Enter') {
      handleSend();
    }
  };
  //--------------------------------------------------------------------------------------------------------
  // loades opportunity to the wave-viewer operated from the chatbot - 
  // tcsd stands for Trend Chart Start Date
  const loadOppWV = (rid,date,tcsd,symbol,days,years) => {
    props.SetOpportunities([])
    props.SetStartDate(date)
    
    let trend_chart_start_date = incrementDate(date, -trend_chart_left_gap_days); // set to 2 weeks before  - set in common 
    props.SetTrendChartStartDate(trend_chart_start_date)
    
    props.SetSymbol(symbol)
    props.SetSeasonalYears(years)
    props.SetConsolidatedSeasonalData([])
    
    props.SetDaysOut(days)
    props.SetMonthsAndQtrs('Months & Qtrs')
    
    //let rid = props.reportsList[idx]['resourceID']
    let resource_group = resourceObj[parseInt(rid)]
    
    props.SetReportsDashVisible(false)
    props.SetSelectedSecurity(resource_group)
  }
  //--------------------------------------------------------------------------------------------------------


  //--------------------------------------------------------------------------------------------------------

  //--------------------------------------------------------------------------------------------------------
  return (
    <div
      id="tradewave-chatbot-container"
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        height: '100%',
        boxSizing: 'border-box',
        backgroundColor: 'rgb(245,245,245)',
      }}
    >
      {/* Chatbox Display */}
      <div
        id="chatbox"
        style={{
          flex: 1,
          border: '1px solid #ccc',
          overflowY: 'auto',
          padding: '10px',
          boxSizing: 'border-box',
        }}
      >
        {messages.map((msg, index) => (
          <div key={index}>
            <strong>{msg.role === 'user' ? 'You' : 'TradeWave Bot'}:</strong>
            {msg.isHtml ? (
              <div dangerouslySetInnerHTML={{ __html: msg.text }} />
            ) : (
              <p>{msg.text}</p>
            )}
          </div>
        ))}
      </div>

      {/* Input Field and Button */}
      <div
        style={{
          display: 'flex',
          padding: '10px',
          boxSizing: 'border-box',
        }}
      >
        <input
          type="text"
          id="userInput"
          placeholder="Ask TradeWave Chatbot any questions about TradeWave"
          style={{
            flex: 1,
            padding: '5px',
          }}
          value={userInput}
          onChange={(e) => setUserInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          id="sendButton"
          style={{
            width: '80px',
            marginLeft: '10px',
            padding: '5px',
          }}
          onClick={handleSend}
        >
          Send
        </button>
      </div>
    </div>
  );
}

export default Chatbot;
