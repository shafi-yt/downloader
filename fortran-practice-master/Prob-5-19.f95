program file_read_write
    implicit none
    character(len=20) :: input_file, output_file
    character(len=100) :: iomsg
    integer :: iostat, i_count
    real :: temp 

    write (*,*) 'Enter the input file name: '
    read (*,*) input_file
    write (*,*) 'Enter the output file name: '
    read (*,*) output_file

    open(unit=10, file=input_file, status='old', iostat=iostat, iomsg=iomsg)
    if (iostat /= 0) then
        write (*,*) 'Error opening input file: ', trim(iomsg)
        stop
    end if 

    open(unit=20, file=output_file, status='replace', iostat=iostat, iomsg=iomsg)
    if (iostat /= 0) then
        write (*,*) 'Error opening output file: ', trim(iomsg)
        stop
    end if 

    i_count = 0 

    do
        read(10, *, iostat=iostat) temp

        if (iostat /= 0) then
            write (*,*) 'End of file or read error encountered.'
            exit
        end if

        write(20, '(I0)') nint(temp)
        i_count = i_count + 1
    end do 

    write (*,*) 'Total integers read and written: ', i_count
    close(10)
    close(20)

end program file_read_write