/*

  vfd/redline.c - Redline / EM60 (Fuling-family) VFD spindle support for grblHAL.

  Matches the Modbus register map that the Onefinity Buildbotics firmware uses for
  its "Redline VFD" profile (identical to its EM60 profile):

      control (run/stop)  reg 0xA000  : forward = 1, reverse = 2, stop = 6
      speed setpoint      reg 0xA001  : scaled 0..10000 = 0..100 % of max RPM
      speed readback      reg 0x9000
      max frequency read  reg 0x0007  (used to scale the readback to RPM)

  Modbus RTU, function 0x06 (write single register) / 0x03 (read holding registers),
  9600 8N1, slave address 1 (defaults on the Redline/Onefinity spindle kits).

  Selectable at runtime with $395 = Redline VFD (ref id SPINDLE_MY_SPINDLE). The RPM
  range is taken from $30 (max) / $31 (min) - set $30 to the spindle's rated RPM
  (e.g. 24000 for the 80 mm 2.2 kW kit); the 0..10000 setpoint scales against it.

  Part of grblHAL

  Copyright (c) 2026 RealTime CNC RTS-1 project

  grblHAL is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  grblHAL is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with grblHAL. If not, see <http://www.gnu.org/licenses/>.

*/

#include "../shared.h"

#if SPINDLE_ENABLE & (1<<SPINDLE_MY_SPINDLE)

#include <math.h>
#include <string.h>

#include "spindle.h"

// Redline / EM60 register map (see file header).
#define REDLINE_REG_CONTROL   0xA000
#define REDLINE_REG_SETFREQ   0xA001
#define REDLINE_REG_GETFREQ   0x9000
#define REDLINE_REG_MAXFREQ   0x0007
#define REDLINE_CMD_FWD       1
#define REDLINE_CMD_REV       2
#define REDLINE_CMD_STOP      6
#define REDLINE_SETPOINT_FULL 10000.0f  // 0xA001 value at 100 % of max RPM

static uint32_t modbus_address, max_freq = 0, exceptions = 0;
static spindle_id_t spindle_id = -1;
static spindle_ptrs_t *spindle_hal = NULL;
static spindle_state_t spindle_state = {0};
static spindle_data_t spindle_data = {0};
static vfd_state_t vfd_state;
static on_spindle_selected_ptr on_spindle_selected;
static on_report_options_ptr on_report_options;
static settings_changed_ptr settings_changed;
static driver_reset_ptr driver_reset;

static void rx_packet (modbus_message_t *msg);
static void rx_exception (uint8_t code, void *context);

static const modbus_callbacks_t callbacks = {
    .retries = VFD_RETRIES,
    .retry_delay = VFD_RETRY_DELAY,
    .on_rx_packet = rx_packet,
    .on_rx_exception = rx_exception
};

// Read the VFD's max frequency (reg 0x0007) so the speed readback can be scaled to RPM.
static void get_max_freq (void *data)
{
    modbus_message_t cmd = {
        .context = (void *)VFD_GetMaxRPM,
        .crc_check = false,
        .adu[0] = modbus_address,
        .adu[1] = ModBus_ReadHoldingRegisters,
        .adu[2] = REDLINE_REG_MAXFREQ >> 8,
        .adu[3] = REDLINE_REG_MAXFREQ & 0xFF,
        .adu[4] = 0x00,
        .adu[5] = 0x01,
        .tx_length = 8,
        .rx_length = 7
    };

    modbus_send(&cmd, &callbacks, true);
}

// Convert a raw readback word (reg 0x9000) to RPM.
// The setpoint scale (0..REDLINE_SETPOINT_FULL) is used as a fallback until the VFD's
// max frequency has been read, then readback is (freq / max_freq) * rpm_max.
static float f2rpm (uint16_t f)
{
    float rpm_max = spindle_hal ? spindle_hal->rpm_max : 0.0f;
    float scale = max_freq ? (float)max_freq : REDLINE_SETPOINT_FULL;

    return ((float)f / scale) * rpm_max;
}

static bool spindleConfig (spindle_ptrs_t *spindle)
{
    return modbus_isup().rtu;
}

// Write the scaled (0..10000) speed setpoint to reg 0xA001.
static void set_rpm (float rpm, bool block)
{
    static uint8_t busy = 0;

    if(busy && !block)
        return;

    float rpm_max = spindle_hal ? spindle_hal->rpm_max : 0.0f;
    uint16_t data = rpm_max > 0.0f ? (uint16_t)((rpm / rpm_max) * REDLINE_SETPOINT_FULL) : 0;

    if(data > (uint16_t)REDLINE_SETPOINT_FULL)
        data = (uint16_t)REDLINE_SETPOINT_FULL;

    modbus_message_t rpm_cmd = {
        .context = (void *)VFD_SetRPM,
        .crc_check = false,
        .adu[0] = modbus_address,
        .adu[1] = ModBus_WriteRegister,
        .adu[2] = REDLINE_REG_SETFREQ >> 8,
        .adu[3] = REDLINE_REG_SETFREQ & 0xFF,
        .adu[4] = data >> 8,
        .adu[5] = data & 0xFF,
        .tx_length = 8,
        .rx_length = 8
    };

    busy++;
    modbus_send(&rpm_cmd, &callbacks, block);
    spindle_set_at_speed_range(spindle_hal, &spindle_data, rpm);
    busy--;
}

static void spindleUpdateRPM (spindle_ptrs_t *spindle, float rpm)
{
    UNUSED(spindle);

    set_rpm(rpm, false);
}

// Start or stop spindle - all via the shared control register 0xA000.
static void spindleSetState (spindle_ptrs_t *spindle, spindle_state_t state, float rpm)
{
    UNUSED(spindle);

    static bool busy = false;

    if(busy)
        return;

    if(state.on && vfd_state != VFD_Ready)
        get_max_freq(NULL);

    uint16_t runstop;

    if(!state.on || rpm == 0.0f)
        runstop = REDLINE_CMD_STOP;
    else
        runstop = state.ccw ? REDLINE_CMD_REV : REDLINE_CMD_FWD;

    modbus_message_t mode_cmd = {
        .context = (void *)VFD_SetStatus,
        .crc_check = true,
        .adu[0] = modbus_address,
        .adu[1] = ModBus_WriteRegister,
        .adu[2] = REDLINE_REG_CONTROL >> 8,
        .adu[3] = REDLINE_REG_CONTROL & 0xFF,
        .adu[4] = runstop >> 8,
        .adu[5] = runstop & 0xFF,
        .tx_length = 8,
        .rx_length = 8
    };

    busy = true;

    if(spindle_state.ccw != state.ccw)
        spindle_data.rpm_programmed = -1.0f;

    spindle_state.on = spindle_data.state_programmed.on = state.on;
    spindle_state.ccw = spindle_data.state_programmed.ccw = state.ccw;

    if(modbus_send(&mode_cmd, &callbacks, true))
        set_rpm(rpm, true);

    busy = false;
}

static spindle_data_t *spindleGetData (spindle_data_request_t request)
{
    return &spindle_data;
}

// Poll the speed readback (reg 0x9000); returns the cached state (response handled async).
static spindle_state_t spindleGetState (spindle_ptrs_t *spindle)
{
    if(vfd_state != VFD_Ready)
        return spindle_state;

    modbus_message_t mode_cmd = {
        .context = (void *)VFD_GetRPM,
        .crc_check = false,
        .adu[0] = modbus_address,
        .adu[1] = ModBus_ReadHoldingRegisters,
        .adu[2] = REDLINE_REG_GETFREQ >> 8,
        .adu[3] = REDLINE_REG_GETFREQ & 0xFF,
        .adu[4] = 0x00,
        .adu[5] = 0x01,
        .tx_length = 8,
        .rx_length = 7
    };

    modbus_send(&mode_cmd, &callbacks, false);

    spindle_state.at_speed = spindle->get_data(SpindleData_AtSpeed)->state_programmed.at_speed;

    return spindle_state;
}

static void rx_packet (modbus_message_t *msg)
{
    if(spindle_hal && !(msg->adu[0] & 0x80)) {

        switch((vfd_response_t)msg->context) {

            case VFD_SetStatus:
                vfd_state = VFD_Ready;
                break;

            case VFD_GetRPM:
                exceptions = 0;
                spindle_validate_at_speed(spindle_data, f2rpm((msg->adu[3] << 8) | msg->adu[4]));
                break;

            case VFD_GetMaxRPM:
                max_freq = (msg->adu[3] << 8) | msg->adu[4];
                vfd_state = VFD_Ready;
                break;

            default:
                break;
        }
    }
}

static void rx_exception (uint8_t code, void *context)
{
    if((vfd_response_t)context != VFD_GetRPM || ++exceptions == VFD_ASYNC_EXCEPTION_LEVEL) {
        exceptions = 0;
        vfd_failed(false);
    }
}

static void onReportOptions (bool newopt)
{
    on_report_options(newopt);

    if(!newopt)
        report_plugin("Redline VFD", "0.01");
}

static void onDriverReset (void)
{
    driver_reset();

    if(spindle_hal)
        task_run_on_reset(get_max_freq, NULL);
}

static void onSpindleSelected (spindle_ptrs_t *spindle)
{
    if(spindle->id == spindle_id) {

        spindle_data.rpm_programmed = -1.0f;
        vfd_atspeed_configure((spindle_hal = spindle), &spindle_data);

        modbus_set_silence(NULL);
        modbus_address = vfd_get_modbus_address(spindle_id);

        get_max_freq(NULL);

    } else
        spindle_hal = NULL;

    if(on_spindle_selected)
        on_spindle_selected(spindle);
}

static void settingsChanged (settings_t *settings, settings_changed_flags_t changed)
{
    settings_changed(settings, changed);

    if(changed.spindle)
        spindle_get_hal(spindle_id, SpindleHAL_Configured)->at_speed_tolerance = vfd_atspeed_configure(spindle_hal, &spindle_data);
}

void vfd_redline_init (void)
{
    static const vfd_spindle_ptrs_t vfd = {
        .spindle = {
            .type = SpindleType_VFD,
            .ref_id = SPINDLE_MY_SPINDLE,
            .cap = {
                .variable = On,
                .at_speed = On,
                .direction = On,
                .cmd_controlled = On
            },
            .config = spindleConfig,
            .set_state = spindleSetState,
            .get_state = spindleGetState,
            .update_rpm = spindleUpdateRPM,
            .get_data = spindleGetData,
        }
    };

    if((spindle_id = vfd_register(&vfd, "Redline VFD")) != -1) {

        on_spindle_selected = grbl.on_spindle_selected;
        grbl.on_spindle_selected = onSpindleSelected;

        settings_changed = hal.settings_changed;
        hal.settings_changed = settingsChanged;

        on_report_options = grbl.on_report_options;
        grbl.on_report_options = onReportOptions;

        driver_reset = hal.driver_reset;
        hal.driver_reset = onDriverReset;
    }
}

#endif
