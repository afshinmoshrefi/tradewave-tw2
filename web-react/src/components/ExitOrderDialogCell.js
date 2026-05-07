import React, { useState, useContext } from 'react';
import NumberPicker from './NumberPicker';
import './styles/ExitOrderDialog.css'
import SelectBox from './SelectBox'
import TextBox from './TextBox'
import { themeColors } from './Common'
import { UserContext } from './UserContext'


const ExitOrderDialogCell = ({
  dialogRef,
  SetSelectedExitContractNumber,
  selectedExitContractNumber,
  displayedPosition,
  displayedPositionIndex,
  toggleExitDialog,
  tradePositions,
  exitStockGain,
  SetExitStockGain,
  exitStockLoss,
  SetExitStockLoss,

  exitOptionGain,
  SetExitOptionGain,
  exitOptionLoss,
  SetExitOptionLoss,
  daysAfter,
  SetDaysAfter,
  daysBefore,
  SetDaysBefore,
  daysAfterGain,
  SetDaysAfterGain,

  handleCreateExitOrder,

  waveEndActionsList,
  waveEndAction,
  SetWaveEndAction,

  earlyExcerciseActionsList,
  earlyExcerciseAction,
  SetEarlyExcerciseAction,

  cellType

}) => {

  const { UITheme } = useContext(UserContext)
  const tc = themeColors(UITheme)

  var paddingTopCell = '6%';
  var paddingBottomCell = '6%';

  var textbox_width = '5';

  const selectboxChanged = (event) => {

    // event.target.id === 'daysout'
    if (event.target.id === 'waveend') {
      SetWaveEndAction(event.target.value)
    }
    else if (event.target.id === 'earlyexcercise') {
      SetEarlyExcerciseAction(event.target.value)
    }

  }



  // cellType could be one of 6
  // 1) 'Stock Profit & Loss'
  // 2) 'Options Profit & Loss'
  // 3) 'After # Days'
  // 4) 'Option Expiration'
  // 5) 'Wave End'
  // 6) 'Early Excercise'


  const handleBlur = (event) => {
   
  }

  return (
    <>
      {/* -----------------------------------------------------------------------------------  */}
      {cellType === 'Stock Profit & Loss' &&
        <div style={{ height: '100%', width: '33.33%', backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', flexDirection: 'column' }}>

          <div className="centered-text" style={{ height: '20%', width: '100%', backgroundColor: tc.titleBar, color: tc.textOnControl }}>Stock Profit</div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingTop: paddingTopCell }}>
            Gain:
            <NumberPicker maxNumber={25} selectedNumber={exitStockGain} setSelectedNumber={SetExitStockGain} suffix={"%"}
            />
          </div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingBottom: paddingBottomCell }}>
            {/* Level: <TextBox text='' width={textbox_width} tbBlur={handleBlur} name="exit_level" /> */}
            {/* <NumberPicker maxNumber={25} selectedNumber={exitStockLoss} setSelectedNumber={SetExitStockLoss} suffix={"%"} />  */}
          </div>
        </div>
      }
      {/* -----------------------------------------------------------------------------------  */}
      {cellType === 'Options Profit & Loss' &&

        <div style={{ height: '100%', width: '33.33%', backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', flexDirection: 'column' }}>

          <div className="centered-text" style={{ height: '20%', width: '100%', backgroundColor: tc.titleBar, color: tc.textOnControl }}>Option Profit</div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingTop: paddingTopCell }}>
            Gain:
            <NumberPicker maxNumber={200} selectedNumber={exitOptionGain} setSelectedNumber={SetExitOptionGain} interval={5} suffix={"%"}
            />
          </div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingBottom: paddingBottomCell }}>
            {/* Loss: */}
            {/* <NumberPicker maxNumber={100} selectedNumber={exitOptionLoss} setSelectedNumber={SetExitOptionLoss} suffix={"%"} */}
            
          </div>
        </div>
      }
      {/* -----------------------------------------------------------------------------------  */}

      {cellType === 'After # Days' &&

        <div style={{ height: '100%', width: '33.33%', backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', flexDirection: 'column' }}>

          <div className="centered-text" style={{ height: '20%', width: '100%', backgroundColor: tc.titleBar, color: tc.textOnControl }}>After # Days</div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingLeft: '32px', paddingTop: paddingTopCell }}>
            Days: &nbsp;
            <NumberPicker maxNumber={30} selectedNumber={daysAfter} setSelectedNumber={SetDaysAfter} showZero={true} />
          </div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', fontSize: '0.9em', paddingBottom: paddingBottomCell }}>
            Option Gain:
            <NumberPicker maxNumber={50} selectedNumber={daysAfterGain} setSelectedNumber={SetDaysAfterGain} showZero={false} suffix={'%'} />
          </div>
        </div>
      }

      {/* -----------------------------------------------------------------------------------  */}

      {cellType === 'Option Expiration' &&

        <div style={{ height: '100%', width: '33.33%', backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', flexDirection: 'column' }}>
          <div className="centered-text" style={{ height: '20%', width: '100%', backgroundColor: tc.titleBar, color: tc.textOnControl }}>Option Expiration</div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingTop: paddingTopCell }}>
            Exit Position
          </div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingBottom: paddingBottomCell }}>
            <NumberPicker maxNumber={30} selectedNumber={daysBefore} setSelectedNumber={SetDaysBefore} showZero={false} />
            &nbsp;Days Before:
          </div>
        </div>

      }
      {/* -----------------------------------------------------------------------------------  */}

      {cellType === 'Wave End' &&

        <div style={{ height: '100%', width: '33.33%', backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', flexDirection: 'column' }}>
          <div className="centered-text" style={{ height: '20%', width: '100%', backgroundColor: tc.titleBar, color: tc.textOnControl }}>Wave End</div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingTop: paddingTopCell }}>
            Wave End
          </div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingBottom: paddingBottomCell }}>

            <SelectBox optionList={waveEndActionsList} value={waveEndAction} name="waveend" sbChanged={selectboxChanged} />
          </div>
        </div>
      }
      {/* -----------------------------------------------------------------------------------  */}

      {cellType === 'Early Excercise' &&

        <div style={{ height: '100%', width: '33.33%', backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', flexDirection: 'column' }}>
          <div className="centered-text" style={{ height: '20%', width: '100%', backgroundColor: tc.titleBar, color: tc.textOnControl }}>Early Excercise</div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingTop: paddingTopCell }}>
            Early Excercise
          </div>
          <div className="centered-text" style={{ height: '40%', width: '100%', backgroundColor: 'transparent', paddingBottom: paddingBottomCell }}>

            <SelectBox optionList={earlyExcerciseActionsList} value={earlyExcerciseAction} name="earlyexcercise" sbChanged={selectboxChanged} />
          </div>
        </div>
      }


      {/* -----------------------------------------------------------------------------------  */}



    </>
  );
};

export default ExitOrderDialogCell;








