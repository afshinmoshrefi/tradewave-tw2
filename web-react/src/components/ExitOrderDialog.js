import React, { useState, useContext } from 'react';
import NumberPicker from './NumberPicker';
import './styles/ExitOrderDialog.css'
import { GrClose } from "react-icons/gr";
import ExitOrderDialogCell from './ExitOrderDialogCell'
import { UserContext } from './UserContext'



const ExitOrderDialog = ({
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
  SetEarlyExcerciseAction


}) => {

  const { browserH, browserW, rdd } = useContext(UserContext)

  const exitOrderProps = {
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
    SetEarlyExcerciseAction
  };

  //-- vars based on the device

  var dWidth = '24%';
  var positionPaddingRight = '10%'

  if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { dWidth = '100%'; positionPaddingRight = '4%' }
  else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { }
  else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { }
  else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { }


  return (
    <dialog ref={dialogRef} style={{ width: dWidth, height: '45%', top: '20%' }} >

      <div style={{ width: '100%', height: '100%', backgroundColor: 'transparent', userSelect: 'none' }} >
        {/* title bar  */}
        <div style={{ paddingLeft: '0.4vw', width: '100%', height: '8%', backgroundColor: 'gray', color: 'white', display: 'flex' }}>

          <div style={{ width: '80%', height: '100%', display: 'flex', justifyContent: 'flex-start', alignItems: "center", fontSize: '1.2em', fontWeight: 'bold', paddingLeft: '5px' }}>Custom Exit Order</div>
          <div style={{ width: '20%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: "center" }}><GrClose size={18} style={{ backgroundColor: 'lightgray', marginRight: '6px' }} onClick={toggleExitDialog} /></div>

        </div>

        {/* first row  */}
        <div style={{ width: '100%', height: '14%', backgroundColor: 'snow', fontWeight: 'bold', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRight: '1px solid lightgray', borderLeft: '1px solid lightgray' }}>

          <div style={{ width: '100%', height: '100%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span>Exit Order for   &nbsp;&nbsp; </span>
            {tradePositions.length > 0 &&
              <NumberPicker
                maxNumber={tradePositions[displayedPositionIndex]['leg0']['quantity']}
                selectedNumber={selectedExitContractNumber}
                setSelectedNumber={SetSelectedExitContractNumber}
                showZero={false}
                zeroStart={false}
              />
            }
            &nbsp;&nbsp; {selectedExitContractNumber === 1 ? 'Contract' : 'Contracts'}
          </div>


        </div>
        {/* position div  */}

        <div style={{ width: '100%', height: '14%', backgroundColor: 'lightgray', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'row', fontWeight: 'bold', color: 'black' }}>

          <div style={{ fontSize: '0.8em', width: '67%', height: '100%', backgroundColor: 'transparent', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', flexDirection: 'column', paddingRight: positionPaddingRight }}>
            {/* this ternery below is because initially displayPosition['row0'] is undefined  */}
            <div>{displayedPosition['row0'] ? displayedPosition['row0'].replace('**', selectedExitContractNumber) : ''}</div>
            <div>{displayedPosition['row1'] ? displayedPosition['row1'].replace('**', selectedExitContractNumber) : ''}</div>
          </div>
          <div style={{ width: '33%', height: '100%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>

            <button onClick={() => { handleCreateExitOrder('market'); toggleExitDialog() }}>Market Order</button>
          </div>

        </div>

        {/* ########################################################################### */}
        {/* this is where the 3x2 side by side windows for gain and loss starts  */}
        {/* ########################################################################### */}
        <div style={{ width: '100%', height: '54%', backgroundColor: 'lightgray', borderBottom: '1px solid gray', display: 'flex', flexDirection: 'column' }}>

          <div style={{ width: '100%', height: '50%', backgroundColor: 'transparent', borderBottom: '1px solid gray', display: 'flex', display: 'flex' }}>

            <ExitOrderDialogCell {...exitOrderProps} cellType={'Stock Profit & Loss'} />
            <ExitOrderDialogCell {...exitOrderProps} cellType={'Options Profit & Loss'} />
            <ExitOrderDialogCell {...exitOrderProps} cellType={'After # Days'} />


          </div>

          <div style={{ width: '100%', height: '50%', backgroundColor: 'transparent', borderBottom: '1px solid gray', display: 'flex' }}>
            <ExitOrderDialogCell {...exitOrderProps} cellType={'Option Expiration'} />
            <ExitOrderDialogCell {...exitOrderProps} cellType={'Wave End'} />
            <ExitOrderDialogCell {...exitOrderProps} cellType={'Early Excercise'} />


          </div>

        </div>


        <div style={{ width: '100%', height: '10%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'flex-end', paddingBottom: '4px' }}>
          <button onClick={toggleExitDialog}>Cancel</button>
          &nbsp;&nbsp;&nbsp;
          <button onClick={() => { handleCreateExitOrder('full-exit-order'); toggleExitDialog() }}>Update Exit Order</button>
        </div>

      </div>



    </dialog>
  );
};

export default ExitOrderDialog;








